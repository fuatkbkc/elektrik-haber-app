# ================================================================
# GÜNLÜK ELEKTRİK HABERİ (TR & EN - TRENDLİ) + TWEET + VERİ GÖRÜNÜMÜ
# ================================================================


import re
import io
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta, date
import warnings


warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

st.set_page_config(page_title="Günlük Elektrik Haberi", layout="wide")




# ****************************************************************
# *** SESSION STATE BAŞLANGIÇ DEĞERLERİ ***
# ****************************************************************

if "en_trend_text" not in st.session_state:
    st.session_state["en_trend_text"] = ""

if "en_trend_headline" not in st.session_state:
    st.session_state["en_trend_headline"] = ""

if "en_trend_spot" not in st.session_state:
    st.session_state["en_trend_spot"] = ""

if "en_trend_body" not in st.session_state:
    st.session_state["en_trend_body"] = ""

if "last_date" not in st.session_state:
    st.session_state["last_date"] = None

if "tr_tweet" not in st.session_state:
    st.session_state["tr_tweet"] = ""

if "en_tweet" not in st.session_state:
    st.session_state["en_tweet"] = ""




# ****************************************************************
# *** GENEL SABİTLER ***
# ****************************************************************

EN_BYLINE_NAME = "By"
EN_BYLINE_AGENCY = "Anadolu Agency"
EN_BYLINE_EMAIL = "energy@aa.com.tr"

TR_HEADLINE = "Günlük elektrik üretim ve tüketim verileri"

# Tweet linkleri (örnek - gerçek linklerle değiştirin)
TR_TWEET_LINK = "http://et.aa.com.tr/52806"
EN_TWEET_LINK = "https://aa.com.tr/en/energy/electricity/turkiyes-daily-power-consumption-up-156-on-nov-10/52808"




# ****************************************************************
# *** YARDIMCI FONKSİYONLAR ***
# ****************************************************************

def find_header_row(df, must_have_cols, search_rows=40):
    for i in range(min(search_rows, len(df))):
        row_vals = df.iloc[i].astype(str).tolist()
        if all(any(mh == cell for cell in row_vals) for mh in must_have_cols):
            return i
    for i in range(min(search_rows, len(df))):
        row_vals = df.iloc[i].astype(str).tolist()
        if all(any(mh.lower() in str(cell).lower() for cell in row_vals) for mh in must_have_cols):
            return i
    raise RuntimeError(f"Başlık satırı bulunamadı: {must_have_cols}")



# ---------- SAYILARI TÜRKÇE BİÇİME DÖNÜŞTÜR ----------
def tr_number_words(num):
    try:
        n = int(round(float(num)))
    except Exception:
        return str(num)
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        th, rem = n // 1000, n % 1000
        return f"{th} bin" if rem == 0 else f"{th} bin {rem}"
    mil, rem = n // 1_000_000, n % 1_000_000
    th, last = rem // 1000, rem % 1000
    if th == 0 and last == 0: return f"{mil} milyon"
    if last == 0:            return f"{mil} milyon {th} bin"
    return f"{mil} milyon {th} bin {last}"



def tr_percent(x):   # 23.8 -> "23,8"
    return str(round(float(x), 1)).replace(".", ",")



# ---------- SAYILARI ENGLISH BİÇİME DÖNÜŞTÜR ----------
def en_int(n):       # 894465 -> "894,465"
    return f"{int(round(float(n))):,}"



def en_percent(x):   # 23.8 -> "23.8"
    return f"{round(float(x), 1):.1f}"



def en_date_from_ddmmyyyy(s):  # "30.10.2025" -> "Oct. 30"
    dt = datetime.strptime(s, "%d.%m.%Y")
    month_names = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "Jun.", "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec."]
    return f"{month_names[dt.month-1]} {dt.day}"



def en_weekday_from_ddmmyyyy(s):  # "30.10.2025" -> "Friday"
    dt = datetime.strptime(s, "%d.%m.%Y")
    return dt.strftime("%A")




# ****************************************************************
# *** TEİAŞ RAPORLARINDAN VERİ OKUMA (GÜNLÜK & KARIŞIM) ***
# ****************************************************************

def load_daily_totals(xls):
    df_raw = pd.read_excel(xls, sheet_name="Rapor232", header=None)
    hdr = find_header_row(df_raw, ["GÜN", "ÜRETİM", "İHRACAT", "İTHALAT", "TÜKETİM"])
    df = df_raw.copy()
    df.columns = df.iloc[hdr].tolist()
    df = df.iloc[hdr + 1:].reset_index(drop=True)
    for col in ["ÜRETİM", "İHRACAT", "İTHALAT", "TÜKETİM"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    is_date = df["GÜN"].astype(str).str.match(r"\d{2}\.\d{2}\.\d{4}")
    df = df[is_date & (df["TÜKETİM"] > 0)]
    last_row = df.tail(1).iloc[0]
    last_date = str(last_row["GÜN"])
    return last_date, last_row



def load_hourly_extremes(xls):
    df_raw = pd.read_excel(xls, sheet_name="Rapor228", header=None)
    hdr = find_header_row(df_raw, ["SAAT", "TÜKETİM"])
    df = df_raw.copy()
    df.columns = df.iloc[hdr].tolist()
    df = df.iloc[hdr + 1:].reset_index(drop=True)
    df["TÜKETİM"] = pd.to_numeric(df["TÜKETİM"], errors="coerce")
    df["SAAT"] = df["SAAT"].astype(str).str.strip()
    
    # Daha esnek saat formatı kontrolü
    # Hem "18:00" hem "18.00" formatlarını kabul et
    df = df[df["SAAT"].str.match(r"^\d{2}[:.]\d{2}$", na=False)]
    
    # Saat formatını standartlaştır: "18.00" -> "18:00"
    df["SAAT"] = df["SAAT"].str.replace(".", ":", regex=False)
    
    max_row = df.loc[df["TÜKETİM"].idxmax()]
    min_row = df.loc[df["TÜKETİM"].idxmin()]
    return {"max_saat": str(max_row["SAAT"]), "max_mwh": max_row["TÜKETİM"],
            "min_saat": str(min_row["SAAT"]), "min_mwh": min_row["TÜKETİM"]}


def load_mix_shares(xls, last_date):
    df_raw = pd.read_excel(xls, sheet_name="Rapor209", header=None)
    hdr = find_header_row(df_raw, ["TOPLAM (MWh)"])
    df = df_raw.copy()
    df.columns = df.iloc[hdr].tolist()
    df = df.iloc[hdr + 1:].reset_index(drop=True)
    row = df[df["GÜN"].astype(str) == last_date]
    if row.empty:
        row = df.tail(1)
    row = row.iloc[0]
    total = float(row["TOPLAM (MWh)"]) if pd.notna(row["TOPLAM (MWh)"]) else 0.0
    def pct(col):
        if total <= 0: return 0.0
        return 100.0 * float(row.get(col, 0) or 0) / total
    return {"ithal": pct("İTHAL KÖMÜR"), "gaz": pct("DOĞAL GAZ"), "linyit": pct("LİNYİT")}




# ****************************************************************
# *** TÜRKÇE HABER METNİ ***
# ****************************************************************


def get_turkish_time_suffix(hour_str):
    """Saat için doğru Türkçe eki döndürür: 18.00'da, 19.00'da, 05.00'te, 03.00'te"""
    # Saati parçala (örn: "18:00" veya "18.00")
    hour_part = hour_str.split(':')[0].split('.')[0]
    
    try:
        hour = int(hour_part)
        # Türkçe ses uyumu kuralları:
        # - 18, 19 gibi büyük saatlerde "da" 
        # - 05, 06, 07 gibi küçük saatlerde "te"
        # - 17:00 gibi ara saatler için son rakama göre karar ver
        if hour in [6, 9,10,16, 19, 0]:
            return "da"
        elif hour in [3, 4, 5, 13, 14, 15, 23]:
            return "te"
        elif hour in [1,2, 7, 8, 11, 12, 17,18,20,21,22]:
            return "de"
        
    except:
        return "none"  # Hata durumunda varsayılan


def build_turkish_news(xls):
    """TÜRKÇE HABER METNİ ÜRETİR"""
    last_date, day = load_daily_totals(xls)
    hrs = load_hourly_extremes(xls)
    mix = load_mix_shares(xls, last_date)

    # Saat formatını Türkçe'ye uygun hale getir ve doğru ekleri al
    max_saat_tr = hrs['max_saat'].replace(":", ".")
    min_saat_tr = hrs['min_saat'].replace(":", ".")
    
    max_suffix = get_turkish_time_suffix(hrs['max_saat'])
    min_suffix = get_turkish_time_suffix(hrs['min_saat'])

    tr_body = f"""
ANKARA (AA) - Türkiye'de dün günlük bazda {tr_number_words(day['ÜRETİM'])} megavatsaat elektrik üretildi, tüketim ise {tr_number_words(day['TÜKETİM'])} megavatsaat oldu.

Türkiye Elektrik İletim AŞ verilerine göre, saatlik bazda dün en yüksek elektrik tüketimi {tr_number_words(hrs['max_mwh'])} megavatsaatle {max_saat_tr}'{max_suffix}, en düşük tüketim ise {tr_number_words(hrs['min_mwh'])} megavatsaatle {min_saat_tr}'{min_suffix} gerçekleşti.

Günlük bazda dün {tr_number_words(day['ÜRETİM'])} megavatsaat elektrik üretildi, tüketim ise {tr_number_words(day['TÜKETİM'])} megavatsaat olarak kayıtlara geçti.

Üretimde ilk sırada yüzde {tr_percent(mix['ithal'])} payla ithal kömür santralleri yer aldı. Bunu yüzde {tr_percent(mix['gaz'])} ile doğal gaz santralleri ve yüzde {tr_percent(mix['linyit'])} ile linyit santralleri izledi.

Türkiye, dün {tr_number_words(day['İHRACAT'])} megavatsaat elektrik ihracatı, {tr_number_words(day['İTHALAT'])} megavatsaat elektrik ithalatı yaptı.
    """.strip()

    tr_full = f"{TR_HEADLINE}\n\n{tr_body}"
    return tr_full





# ****************************************************************
# *** TÜRKÇE TWEET ***
# ****************************************************************

def build_turkish_tweet(xls):
    """TÜRKÇE TWEET METNİ ÜRETİR"""
    last_date, day = load_daily_totals(xls)
    mix = load_mix_shares(xls, last_date)
    
    tweet = f"""⚡️Türkiye'de dün günlük bazda {tr_number_words(day['ÜRETİM'])} megavatsaat elektrik üretildi, tüketim ise {tr_number_words(day['TÜKETİM'])} megavatsaat oldu

🏭Üretimde ilk sırada yüzde {tr_percent(mix['ithal'])} payla ithal kömür santralleri yer aldı

🔗{TR_TWEET_LINK}"""
    
    return tweet




# ****************************************************************
# *** TRENDLİ İNGİLİZCE HABER ***
# ****************************************************************

def parse_prev_article_tr(text):
    """ÖNCEKİ GÜN TÜRKÇE HABERDEN TÜKETİM VE ÜRETİM VERİLERİNİ ÇEKER"""
    if not text:
        print("🚨 DEBUG: Boş metin!")
        return None
    
    result = {"consumption": None, "production": None}
    t = " ".join(text.strip().split())
    
    print(f"🔍 DEBUG: Aranacak metin (ilk 300 karakter): {t[:300]}")
    
    # METNİ ANALİZ ET: Hangi sayının üretim, hangisinin tüketim olduğunu anlamak için
    # İlk cümleyi bul: "774 bin 839 megavatsaat elektrik üretildi, tüketim ise 769 bin 52 megavatsaat oldu"
    
    # Pattern: "X bin Y megavatsaat elektrik üretildi, tüketim ise A bin B megavatsaat oldu"
    main_pattern = r'(\d+)\s*bin\s*(\d+)\s*megavatsaat\s*elektrik\s*üretildi[^,]*,?\s*tüketim\s*ise\s*(\d+)\s*bin\s*(\d+)\s*megavatsaat'
    
    m = re.search(main_pattern, t, flags=re.IGNORECASE)
    if m:
        try:
            # Grupları al
            prod_bin = int(m.group(1))
            prod_rem = int(m.group(2))
            cons_bin = int(m.group(3))
            cons_rem = int(m.group(4))
            
            # Sayıları hesapla
            production = prod_bin * 1000 + prod_rem  # 774 bin 839 = 774839
            consumption = cons_bin * 1000 + cons_rem  # 769 bin 52 = 769052
            
            result["production"] = production
            result["consumption"] = consumption
            
            print(f"✅ DEBUG: ANA PATTERN BULUNDU!")
            print(f"✅ DEBUG: ÜRETİM: {prod_bin} bin {prod_rem} = {production}")
            print(f"✅ DEBUG: TÜKETİM: {cons_bin} bin {cons_rem} = {consumption}")
            return result
            
        except Exception as e:
            print(f"❌ DEBUG: Ana pattern hatası: {e}")
    
    # Eğer ana pattern bulunamazsa, bireysel pattern'lerle dene
    print("🔄 DEBUG: Ana pattern bulunamadı, bireysel pattern'ler deneniyor...")
    
    # ÖNCE ÜRETİM'i ara - "üretildi" kelimesiyle
    production_patterns = [
        r'(\d+)\s*bin\s*(\d+)\s*megavatsaat\s*elektrik\s*üretildi',
        r'üretildi[^.]*?(\d+)\s*bin\s*(\d+)\s*megavatsaat',
        r'üretim[^.]*?(\d+)\s*bin\s*(\d+)\s*megavatsaat',
    ]
    
    for i, pattern in enumerate(production_patterns):
        m = re.search(pattern, t, flags=re.IGNORECASE)
        if m:
            try:
                bin_part = int(m.group(1))
                remainder = int(m.group(2))
                result["production"] = bin_part * 1000 + remainder
                print(f"✅ DEBUG: ÜRETİM BULUNDU! Pattern {i}: {bin_part} bin {remainder} = {result['production']}")
                break
            except Exception as e:
                print(f"❌ DEBUG: Üretim hatası Pattern {i}: {e}")
    
    # SONRA TÜKETİM'i ara - "tüketim" kelimesiyle
    consumption_patterns = [
        r'tüketim[^.]*?(\d+)\s*bin\s*(\d+)\s*megavatsaat',
        r'(\d+)\s*bin\s*(\d+)\s*megavatsaat[^.]*?tüketim',
        r'tüketim[^.]*?(\d+(?:\.\d+)*)\s*megavatsaat',
    ]
    
    for i, pattern in enumerate(consumption_patterns):
        m = re.search(pattern, t, flags=re.IGNORECASE)
        if m:
            try:
                if 'bin' in pattern:
                    bin_part = int(m.group(1))
                    remainder = int(m.group(2))
                    result["consumption"] = bin_part * 1000 + remainder
                    print(f"✅ DEBUG: TÜKETİM BULUNDU! Pattern {i}: {bin_part} bin {remainder} = {result['consumption']}")
                else:
                    clean_num = m.group(1).replace('.', '').replace(' ', '').strip()
                    result["consumption"] = int(clean_num)
                    print(f"✅ DEBUG: TÜKETİM BULUNDU! Pattern {i}: {result['consumption']}")
                break
            except Exception as e:
                print(f"❌ DEBUG: Tüketim hatası Pattern {i}: {e}")
    
    print(f"📊 DEBUG: Sonuç -> ÜRETİM: {result['production']}, TÜKETİM: {result['consumption']}")
    
    # DOĞRULAMA: Mantıksal kontrol
    if result["production"] and result["consumption"]:
        # Genellikle üretim tüketimden biraz fazladır
        if result["production"] < result["consumption"]:
            print("⚠️ DEBUG: Üretim tüketimden küçük, değerler ters olabilir!")
            # Değerleri swap et
            result["production"], result["consumption"] = result["consumption"], result["production"]
            print(f"🔄 DEBUG: Değerler swap edildi -> ÜRETİM: {result['production']}, TÜKETİM: {result['consumption']}")
        
        return result
    elif result["production"] or result["consumption"]:
        print("⚠️ DEBUG: Sadece bir değer bulundu")
        return result
    else:
        print("❌ DEBUG: Hiçbir değer bulunamadı")
        return None        
    return None
    
    
def build_english_trend(xls, prev_text):
    """TREND İNGİLİZCE HABER - TAM İSTENEN FORMATTA"""
    print("🚀 DEBUG: build_english_trend fonksiyonu ÇALIŞTI!")
    
    last_date, day = load_daily_totals(xls)
    hrs = load_hourly_extremes(xls)
    mix = load_mix_shares(xls, last_date)
    
    # Mevcut gün verileri
    curr_consumption = float(day["TÜKETİM"])  # Bugünkü TÜKETİM
    curr_production = float(day["ÜRETİM"])    # Bugünkü ÜRETİM
    
    print(f"📅 DEBUG: Bugünkü tarih: {last_date}")
    print(f"🔢 DEBUG: Bugünkü TÜKETİM: {curr_consumption}")
    print(f"🔢 DEBUG: Bugünkü ÜRETİM: {curr_production}")
    
    # Önceki gün verilerini parse et
    prev_data = None
    if prev_text and prev_text.strip():
        prev_data = parse_prev_article_tr(prev_text)
    
    # YÜZDE DEĞİŞİMLERİ HESAPLA - DOĞRU KARŞILAŞTIRMA
    consumption_pct_str = "0"
    production_pct_str = "0"
    direction = "up"
    production_direction_word = "rise"
    
    print(f"🔢 DEBUG: Önceki TÜKETİM: {prev_data.get('consumption') if prev_data else 'YOK'}")
    print(f"🔢 DEBUG: Önceki ÜRETİM: {prev_data.get('production') if prev_data else 'YOK'}")
    
    # DOĞRU KARŞILAŞTIRMA: Tüketim vs Tüketim
    if prev_data and prev_data.get("consumption") and prev_data["consumption"] > 0:
        prev_consumption = float(prev_data["consumption"])  # Önceki gün TÜKETİM
        consumption_pct = (curr_consumption - prev_consumption) / prev_consumption * 100.0
        print(f"📊 DEBUG: TÜKETİM yüzde değişimi: {consumption_pct:.2f}%")
        print(f"📊 DEBUG: Tüketim Formülü: ({curr_consumption} - {prev_consumption}) / {prev_consumption} * 100")
        
        if abs(consumption_pct) > 1000:
            consumption_pct_str = "N/A"
            direction = "up" if consumption_pct >= 0 else "down"
        else:
            consumption_pct_str = f"{abs(consumption_pct):.1f}"
            direction = "up" if consumption_pct >= 0 else "down"
        print(f"✅ DEBUG: Tüketim sonuç: {consumption_pct_str}% ({direction})")
    else:
        print("❌ DEBUG: Önceki TÜKETİM verisi yok")
    
    # DOĞRU KARŞILAŞTIRMA: Üretim vs Üretim  
    if prev_data and prev_data.get("production") and prev_data["production"] > 0:
        prev_production = float(prev_data["production"])  # Önceki gün ÜRETİM
        production_pct = (curr_production - prev_production) / prev_production * 100.0
        print(f"📊 DEBUG: ÜRETİM yüzde değişimi: {production_pct:.2f}%")
        print(f"📊 DEBUG: Üretim Formülü: ({curr_production} - {prev_production}) / {prev_production} * 100")
        
        if abs(production_pct) > 1000:
            production_pct_str = "N/A"
            production_direction_word = "rise" if production_pct >= 0 else "fall"
        else:
            production_pct_str = f"{abs(production_pct):.1f}"
            production_direction_word = "rise" if production_pct >= 0 else "fall"
        print(f"✅ DEBUG: Üretim sonuç: {production_pct_str}% ({production_direction_word})")
    else:
        print("❌ DEBUG: Önceki ÜRETİM verisi yok")
        print("❌ DEBUG: Önceki üretim verisi yok veya geçersiz")
        
        production_pct_str = "0"
        production_direction_word = "rise"
    
    # Kalan kod aynı...
    mix = load_mix_shares(xls, last_date)
    hrs = load_hourly_extremes(xls)
    
    date_en = en_date_from_ddmmyyyy(last_date)
    weekday_en = en_weekday_from_ddmmyyyy(last_date)
    prev_date = (datetime.strptime(last_date, "%d.%m.%Y") - timedelta(days=1)).strftime("%d.%m.%Y")
    prev_weekday = en_weekday_from_ddmmyyyy(prev_date)
    report_date = (datetime.strptime(last_date, "%d.%m.%Y") + timedelta(days=1)).strftime("%d.%m.%Y")
    report_weekday = en_weekday_from_ddmmyyyy(report_date)
    
    # HEADLINE
    headline = f"Türkiye's daily power consumption {direction} {consumption_pct_str}% on {date_en}"
    
    # SPOT
    spot = f"- Electricity exports amount to {en_int(day['İHRACAT'])} megawatt-hours and imports total {en_int(day['İTHALAT'])} megawatt-hours"
    
    # BODY
    body = (
        f"Daily electricity consumption in Türkiye {'increased' if direction == 'up' else 'decreased'} "
        f"around {consumption_pct_str}% on {weekday_en} compared to the previous day, totaling {en_int(curr_consumption)} "
        f"megawatt-hours, according to official figures of Turkish Electricity Transmission Corporation (TEIAS) released on {report_weekday}.\n\n"
        f"Electricity production amounted to {en_int(curr_production)} megawatt-hours on {weekday_en}, marking a {production_direction_word} "
        f"of {production_pct_str}% compared to {prev_weekday}.\n\n"
        f"Electricity production from imported coal plants accounted for around {en_percent(mix['ithal'])}% of total generation, while natural gas and lignite contributed "
        f"{en_percent(mix['gaz'])}% and {en_percent(mix.get('linyit', 0))}%, respectively.\n\n"
        f"On {weekday_en}, the country's electricity exports totaled {en_int(day['İHRACAT'])} megawatt-hours, while imports amounted to {en_int(day['İTHALAT'])} megawatt-hours.\n\n"
        f"{EN_BYLINE_NAME}\n{EN_BYLINE_AGENCY}\n{EN_BYLINE_EMAIL}"
    )
    
    full = f"{headline}\n{spot}\n\n{body}"
    
    return {
        "headline": headline,
        "spot": spot,
        "body": body,
        "full": full
    }



# ****************************************************************
# *** İNGİLİZCE TWEET ***
# ****************************************************************

def build_english_tweet(xls, prev_text):
    """İNGİLİZCE TWEET METNİ ÜRETİR"""
    last_date, day = load_daily_totals(xls)
    
    # Önceki gün verilerini parse et (TÜRKÇE metinden)
    prev_data = parse_prev_article_tr(prev_text)
    
    # Mevcut gün verileri
    curr_consumption = float(day["TÜKETİM"])
    
    # Tarih formatları
    weekday_en = en_weekday_from_ddmmyyyy(last_date)
    report_date = (datetime.strptime(last_date, "%d.%m.%Y") + timedelta(days=1)).strftime("%d.%m.%Y")
    report_weekday = en_weekday_from_ddmmyyyy(report_date)
    
    # Yüzde değişim hesapla
    consumption_pct_str = "0"
    direction = "up"
    
    if prev_data and prev_data["consumption"]:
        prev_consumption = prev_data["consumption"]
        
        if prev_consumption > 0:
            consumption_pct = ((curr_consumption - prev_consumption) / prev_consumption) * 100.0
            
            if abs(consumption_pct) <= 1000:
                consumption_pct_str = f"{abs(consumption_pct):.1f}"
                direction = "up" if consumption_pct >= 0 else "down"

    tweet = f"""⚡Daily electricity consumption in Türkiye {'increased' if direction == 'up' else 'decreased'} around {consumption_pct_str}% on {weekday_en} compared to the previous day, totaling {en_int(curr_consumption)} megawatt-hours, according to official figures of Turkish Electricity Transmission Corporation (TEIAS) released on {report_weekday}

🔗{EN_TWEET_LINK}"""
    
    return tweet


# ****************************************************************
# *** ANALİTİK YARDIMCILAR ***
# ****************************************************************

def load_daily_table_df(xls):
    """RAPOR232'Yİ TEMİZLEYİP GÜNLÜK TABLO ÇIKARIR"""
    df_raw = pd.read_excel(xls, sheet_name="Rapor232", header=None)
    hdr = find_header_row(df_raw, ["GÜN", "ÜRETİM", "İHRACAT", "İTHALAT", "TÜKETİM"])
    df = df_raw.copy()
    df.columns = df.iloc[hdr].tolist()
    df = df.iloc[hdr+1:].reset_index(drop=True)
    df = df[df["GÜN"].astype(str).str.match(r"\d{2}\.\d{2}\.\d{4}")]
    for col in ["ÜRETİM","İHRACAT","İTHALAT","TÜKETİM"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["TARİH"] = pd.to_datetime(df["GÜN"], format="%d.%m.%Y")
    df = df[["TARİH","ÜRETİM","İHRACAT","İTHALAT","TÜKETİM"]].sort_values("TARİH")
    return df



def load_mix_daily_df(xls):
    """RAPOR209'DAN GÜNLÜK KAYNAK MİKTARLARI TABLOSU ÇIKARIR"""
    df_raw = pd.read_excel(xls, sheet_name="Rapor209", header=None)
    hdr = find_header_row(df_raw, ["GÜN","TOPLAM (MWh)"])
    df = df_raw.copy()
    df.columns = df.iloc[hdr].tolist()
    df = df.iloc[hdr+1:].reset_index(drop=True)
    df = df[df["GÜN"].astype(str).str.match(r"\d{2}\.\d{2}\.\d{4}")]
    df["TARİH"] = pd.to_datetime(df["GÜN"], format="%d.%m.%Y")
    numeric_cols = [c for c in df.columns if c not in ["GÜN","TARİH"]]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["TARİH"] + [c for c in df.columns if c not in ["GÜN","TARİH"]]]


def monthly_summary_from_232(df232):
    """AYLIK ÖZET TABLOSU OLUŞTURUR"""
    df232['AY'] = df232['TARİH'].dt.to_period('M')
    monthly = df232.groupby('AY').agg({
        'ÜRETİM': 'sum',
        'TÜKETİM': 'sum', 
        'İHRACAT': 'sum',
        'İTHALAT': 'sum'
    }).reset_index()
    monthly['AY'] = monthly['AY'].astype(str)
    return monthly


def monthly_mix_top_source_from_209(df209):
    """AYLIK KAYNAK KARMASI VE EN BASKIN KAYNAK"""
    df209['AY'] = df209['TARİH'].dt.to_period('M')
    
    source_cols = [col for col in df209.columns if col not in ['TARİH', 'AY', 'TOPLAM (MWh)']]
    
    monthly_mix = []
    for period, group in df209.groupby('AY'):
        period_str = str(period)
        year = period_str[:4]
        month = period_str[5:]
        
        source_totals = {}
        for col in source_cols:
            source_totals[col] = group[col].sum()
        
        if source_totals:
            top_source = max(source_totals, key=source_totals.get)
            top_value = source_totals[top_source]
            total_production = sum(source_totals.values())
            top_share = (top_value / total_production * 100) if total_production > 0 else 0
            
            monthly_mix.append({
                'AY': f"{year}-{month}",
                'YIL': year,
                'EN_BASKIN_KAYNAK': top_source,
                'PAY (%)': round(top_share, 1)
            })
    
    return pd.DataFrame(monthly_mix)


# ****************************************************************
# *** YILLIK KARŞILAŞTIRMA ***
# ****************************************************************

def _latest_common_monthday(df_curr, df_prev):
    """İKİ VERİ SETİNDE DE BULUNAN EN SON AY-GÜN'Ü BULUR"""
    md_curr = set(df_curr["TARİH"].dt.strftime("%m-%d"))
    md_prev = set(df_prev["TARİH"].dt.strftime("%m-%d"))
    common = list(md_curr & md_prev)
    if not common:
        return None
    common.sort()
    return common[-1]



def yoy_compare_by_monthday(df232_curr, df232_prev):
    """ORTAK SON AY-GÜN'E KADAR TOPLAYIP YoY KARŞILAŞTIRMA YAPAR"""
    need_cols = {"TARİH","ÜRETİM","TÜKETİM","İHRACAT","İTHALAT"}
    for df_ in (df232_curr, df232_prev):
        if not need_cols.issubset(set(df_.columns)):
            raise ValueError("YoY: 'TARİH, ÜRETİM, TÜKETİM, İHRACAT, İTHALAT' kolonları gerekli.")

    target_md = _latest_common_monthday(df232_curr, df232_prev)
    if target_md is None:
        raise ValueError("YoY: Ortak ay-gün bulunamadı")

    curr_mask = df232_curr["TARİH"].dt.strftime("%m-%d") <= target_md
    prev_mask = df232_prev["TARİH"].dt.strftime("%m-%d") <= target_md

    this_y = df232_curr.loc[curr_mask]
    prev_y = df232_prev.loc[prev_mask]

    sum_curr = this_y[["ÜRETİM","TÜKETİM","İHRACAT","İTHALAT"]].sum(min_count=1)
    sum_prev = prev_y[["ÜRETİM","TÜKETİM","İHRACAT","İTHALAT"]].sum(min_count=1)

    out = pd.DataFrame({
        "METRİK":   ["ÜRETİM","TÜKETİM","İHRACAT","İTHALAT"],
        "BU YIL":   [sum_curr.get("ÜRETİM",0), sum_curr.get("TÜKETİM",0), sum_curr.get("İHRACAT",0), sum_curr.get("İTHALAT",0)],
        "GEÇEN YIL":[sum_prev.get("ÜRETİM",0), sum_prev.get("TÜKETİM",0), sum_prev.get("İHRACAT",0), sum_prev.get("İTHALAT",0)],
    })

    out["DEĞİŞİM (MWh)"] = out["BU YIL"] - out["GEÇEN YIL"]
    out["DEĞİŞİM (%)"] = ((out["DEĞİŞİM (MWh)"] / out["GEÇEN YIL"].replace({0: pd.NA})) * 100).round(1)

    out.attrs["target_monthday"] = target_md
    return out




# ****************************************************************
# *** STREAMLIT ARAYÜZÜ: ÜST HABER BÖLÜMÜ ***
# ****************************************************************

st.title("📰 Günlük Elektrik Haberi (TR & EN)")

col_left, col_right = st.columns(2)



# ---------- SOL SÜTUN ----------
with col_left:
    st.subheader("1️⃣ Previous day (TR) — Paste your previous day's Turkish article")
    prev_text = st.text_area(
        "Paste yesterday's AA Turkish story (for trend)",
        key="prev_text",
        height=160,
        placeholder="Paste yesterday's Turkish article here..."
    )

    cols_btn = st.columns(2)
    with cols_btn[0]:
        if st.button("🧹 Clear previous TR text"):
            st.session_state["prev_text"] = ""
            st.session_state["en_trend_text"] = ""
            st.session_state["en_trend_headline"] = ""
            st.session_state["en_trend_spot"] = ""
            st.session_state["en_trend_body"] = ""
            st.session_state["tr_tweet"] = ""
            st.session_state["en_tweet"] = ""
            st.success("Previous TR text cleared.")

    with cols_btn[1]:
        st.caption("Paste previous TR article, then upload Excel → use Regenerate buttons.")


    st.subheader("2️⃣ Data source")
    mode = st.radio("Source", ["Upload Excel (drag & drop)", "Fetch from web"], horizontal=True)
    xls = None

    if mode == "Upload Excel (drag & drop)":
        uploaded = st.file_uploader(
            "Drop TEİAŞ Excel (.xlsx) here",
            type=["xlsx"],
            accept_multiple_files=False,
            label_visibility="collapsed"
        )
        if uploaded:
            xls = pd.ExcelFile(uploaded)
            st.success("✅ File uploaded successfully.")
    else:
        pick = st.date_input("Pick date (will download from web)", value=date.today())
        if st.button("Download & Load"):
            try:
                with st.spinner("Downloading Excel from TEİAŞ..."):
                    url = f"https://.../GENEL_GUNLUK_ISLETME_NETICESI_{pick:%Y-%m-%d}.xlsx"
                    r = requests.get(url, timeout=30)
                    r.raise_for_status()
                    xls = pd.ExcelFile(io.BytesIO(r.content))
                st.success("✅ Downloaded and loaded.")
            except Exception as e:
                st.error(f"Download error: {e}")



# ---------- SAĞ SÜTUN ----------
with col_right:
    st.subheader("3️⃣ Output")

    # 4 SEKMELİ ARAYÜZ
    tabs = st.tabs(["🇹🇷 Turkish (AA)", "🐦 Turkish Tweet", "🇬🇧 English (trend)", "🐦 English Tweet"])

    if xls is None:
        with tabs[0]:
            st.text_area("Haber (TR)", "⬅️ Excel yüklediğinizde Türkçe haber burada görünecek.", height=350)
        with tabs[1]:
            st.text_area("Tweet (TR)", "⬅️ Excel yüklediğinizde Türkçe tweet burada görünecek.", height=200)
        with tabs[2]:
            st.text_area("News (EN, trend)", "⬅️ Dünkü TÜRKÇE metni yapıştırın ve Excel yükleyin. Ardından 'Regenerate English (trend)' butonuna basın.", height=350)
        with tabs[3]:
            st.text_area("Tweet (EN)", "⬅️ Dünkü TÜRKÇE metni yapıştırın ve Excel yükleyin. Ardından 'Regenerate English Tweet' butonuna basın.", height=200)

    else:
        try:
            with st.spinner("Generating content..."):
                tr_news = build_turkish_news(xls)
                tr_tweet = build_turkish_tweet(xls)

                # EXCEL TARİHİ DEĞİŞTİYSE SIFIRLA
                try:
                    curr_last_date, _ = load_daily_totals(xls)
                except Exception:
                    curr_last_date = None
                if curr_last_date and st.session_state.get("last_date") != curr_last_date:
                    st.session_state["last_date"] = curr_last_date
                    st.session_state["en_trend_text"] = ""
                    st.session_state["en_trend_headline"] = ""
                    st.session_state["en_trend_spot"] = ""
                    st.session_state["en_trend_body"] = ""
                    st.session_state["tr_tweet"] = ""
                    st.session_state["en_tweet"] = ""

            # TÜRKÇE HABER
            with tabs[0]:
                st.text_area("Haber (TR)", tr_news, height=350)
                st.download_button("Download TXT (TR)", tr_news, file_name="haber_tr.txt")

            # TÜRKÇE TWEET
            with tabs[1]:
                if not st.session_state["tr_tweet"]:
                    st.session_state["tr_tweet"] = tr_tweet
                
                st.text_area("Tweet (TR)", st.session_state["tr_tweet"], height=200, key="tr_tweet_area")
                st.download_button("Download TXT (TR Tweet)", st.session_state["tr_tweet"], file_name="tweet_tr.txt")

            # İNGİLİZCE HABER
            with tabs[2]:
                cols_trend = st.columns([1, 1])
                regen_en = cols_trend[0].button("🔁 Regenerate English (trend)", key="btn_regen_en")
                clear_trend = cols_trend[1].button("🧹 Clear trend output", key="btn_clear_trend")

                if clear_trend:
                    st.session_state["en_trend_text"] = ""
                    st.session_state["en_trend_headline"] = ""
                    st.session_state["en_trend_spot"] = ""
                    st.session_state["en_trend_body"] = ""
                    st.session_state["en_tweet"] = ""

                if regen_en or not st.session_state["en_trend_text"]:
                    with st.spinner("Regenerating EN trend..."):
                        comps = build_english_trend(xls, st.session_state.get("prev_text", ""))
                        st.session_state["en_trend_headline"] = comps["headline"]
                        st.session_state["en_trend_spot"] = comps["spot"]
                        st.session_state["en_trend_body"] = comps["body"]
                        st.session_state["en_trend_text"] = comps["full"]

                st.text_area("Headline", st.session_state["en_trend_headline"], height=80, key="en_trend_headline_area")
                st.text_area("Spot", st.session_state["en_trend_spot"], height=80, key="en_trend_spot_area")
                st.text_area("Body", st.session_state["en_trend_body"], height=190, key="en_trend_body_area")
                st.download_button("Download TXT (EN trend - full)", st.session_state["en_trend_text"], file_name="news_en_trend.txt")

            # İNGİLİZCE TWEET
            with tabs[3]:
                cols_tweet = st.columns([1, 1])
                regen_tweet = cols_tweet[0].button("🔁 Regenerate English Tweet", key="btn_regen_en_tweet")
                clear_tweet = cols_tweet[1].button("🧹 Clear tweet", key="btn_clear_en_tweet")

                if clear_tweet:
                    st.session_state["en_tweet"] = ""

                if regen_tweet or not st.session_state["en_tweet"]:
                    with st.spinner("Generating EN tweet..."):
                        en_tweet = build_english_tweet(xls, st.session_state.get("prev_text", ""))
                        st.session_state["en_tweet"] = en_tweet

                st.text_area("Tweet (EN)", st.session_state["en_tweet"], height=200, key="en_tweet_area")
                st.download_button("Download TXT (EN Tweet)", st.session_state["en_tweet"], file_name="tweet_en.txt")

        except Exception as e:
            st.error(f"⚠️ Error: {e}")
            st.exception(e)




# ****************************************************************
# *** ALT BÖLÜM: VERİ GÖRÜNÜMÜ & ANALİTİK ***
# ****************************************************************

st.markdown("---")
st.header("📈 Veri Görünümü & Analitik")

if 'xls' not in locals() or xls is None:
    st.info("Excel yüklendiğinde günlük tablo, aylık özet ve yıllık karşılaştırma burada görünecek.")

else:
    try:
        with st.spinner("Preparing data views..."):
            df232 = load_daily_table_df(xls)
            df209 = load_mix_daily_df(xls)

        # ---------- HAM GÜNLÜK TABLO ----------
        st.subheader("🔹 Günlük Tablo (Rapor232)")
        st.dataframe(df232, use_container_width=True, hide_index=True)
        st.download_button("Download CSV — Günlük Tablo", df232.to_csv(index=False).encode("utf-8"), file_name="gunluk_tablo.csv")



        # ---------- AYLIK ÖZET (RAPOR232) ----------
        st.subheader("🔹 Aylık Özet (Üretim, Tüketim, İhracat, İthalat)")
        monthly_232 = monthly_summary_from_232(df232)
        st.dataframe(monthly_232, use_container_width=True, hide_index=True)
        st.download_button("Download CSV — Aylık Özet", monthly_232.to_csv(index=False).encode("utf-8"), file_name="aylik_ozet_232.csv")



        # ---------- AYLIK KAYNAK KARMASI & EN BASKIN KAYNAK (RAPOR209) ----------
        st.subheader("🔹 Aylık Üretim Karması ve En Baskın Kaynak (Rapor209)")
        monthly_mix = monthly_mix_top_source_from_209(df209)
        st.dataframe(monthly_mix, use_container_width=True, hide_index=True)
        st.download_button("Download CSV — Aylık Karması", monthly_mix.to_csv(index=False).encode("utf-8"), file_name="aylik_kaynak_karmasi_209.csv")

        # KISA CÜMLELER
        st.markdown("**Aylık özet cümleleri:**")
        lines = []
        for _, r in monthly_mix.iterrows():
            if pd.notna(r["EN_BASKIN_KAYNAK"]):
                lines.append(f"- {r['AY']} {int(r['YIL'])} döneminde en fazla üretim **{r['EN_BASKIN_KAYNAK']}** kaynağından yapıldı (yaklaşık **{r['PAY (%)']:.1f}%**).")
        st.markdown("\n".join(lines) if lines else "_Veri yok_")



        # ---------- YILLIK KARŞILAŞTIRMA (ÖNCEKİ YIL EXCEL İSTEĞE BAĞLI) ----------
        st.subheader("🔹 Yıllık Karşılaştırma (YoY) — Önceki yıl Excel'i yükleyin (opsiyonel)")

        prev_year_file = st.file_uploader(
            "Geçen yıla ait TEİAŞ Excel (.xlsx) — Rapor232 içermeli",
            type=["xlsx"],
            key="prev_year_xls"
        )

        if prev_year_file:
            try:
                with st.spinner("Loading previous-year file..."):
                    xls_prev = pd.ExcelFile(prev_year_file)
                    df232_prev = load_daily_table_df(xls_prev)

                yoy = yoy_compare_by_monthday(df232, df232_prev)

                st.dataframe(yoy, use_container_width=True, hide_index=True)
                st.download_button(
                    "Download CSV — Yıllık Karşılaştırma",
                    yoy.to_csv(index=False).encode("utf-8"),
                    file_name="yillik_karsilastirma_yoy.csv"
                )

                tgt_md = yoy.attrs.get("target_monthday")
                if tgt_md:
                    st.caption(f"Karşılaştırma, her iki yılda da mevcut olan **{tgt_md}** tarihine kadar (YTD) yapılmıştır.")

                st.markdown("**Yıllık özet:**")
                try:
                    u = yoy[yoy["METRİK"]=="ÜRETİM"].iloc[0]
                    t = yoy[yoy["METRİK"]=="TÜKETİM"].iloc[0]
                    st.markdown(
                        f"- Üretim (YTD): **{int(u['BU YIL']):,}** MWh (Δ: {int(u['DEĞİŞİM (MWh)']):,} | {u['DEĞİŞİM (%)']}%)  \n"
                        f"- Tüketim (YTD): **{int(t['BU YIL']):,}** MWh (Δ: {int(t['DEĞİŞİM (MWh)']):,} | {t['DEĞİŞİM (%)']}%)"
                    )
                except Exception:
                    st.caption("Özet üretilemedi; tabloya bakınız.")

            except Exception as e:
                st.error(f"YoY hesaplanamadı: {e}")
                st.exception(e)

        else:
            st.caption("Önceki yıl dosyası yüklenirse yıl-yılına (YTD) karşılaştırma tablosu oluşturulur.")

    except Exception as e:
        st.error(f"⚠️ Veri görünümü hazırlanırken hata oluştu: {e}")
        st.exception(e)
