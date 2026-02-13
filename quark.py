
import asyncio
import json
import os
import random
import re
import sys
from typing import Any, Union

import httpx
from prettytable import PrettyTable
from tqdm import tqdm

from quark_login import CONFIG_DIR, QuarkLogin
from utils import custom_print, generate_random_code, get_datetime, get_timestamp, read_config, safe_copy, save_config


class QuarkPanFileManager:
    def __init__(self, headless: bool = False, slow_mo: int = 0) -> None:
        self.headless: bool = headless
        self.slow_mo: int = slow_mo
        self.folder_id: Union[str, None] = None
        self.user: Union[str, None] = '用户A'
        self.pdir_id: Union[str, None] = '0'
        self.dir_name: Union[str, None] = '根目录'
        self.cookies: str = self.get_cookies()
        self.headers: dict[str, str] = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko)'
                          ' Chrome/94.0.4606.71 Safari/537.36 Core/1.94.225.400 QQBrowser/12.2.5544.400',
            'origin': 'https://pan.quark.cn',
            'referer': 'https://pan.quark.cn/',
            'accept-language': 'zh-CN,zh;q=0.9',
            'cookie': self.cookies,
        }

    def get_cookies(self) -> str:
        quark_login = QuarkLogin(headless=self.headless, slow_mo=self.slow_mo)
        cookies: str = quark_login.get_cookies()
        return cookies

    @staticmethod
    def get_pwd_id(share_url: str) -> str:
        return share_url.split('?')[0].split('/s/')[-1]

    @staticmethod
    def extract_urls(text: str) -> list:
        url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
        return re.findall(url_pattern, text)[0]

    async def get_stoken(self, pwd_id: str, password: str = '') -> str:
        params = {
            'pr': 'ucpro',
            'fr': 'pc',
            'uc_param_str': '',
            '__dt': random.randint(100, 9999),
            '__t': get_timestamp(13),
        }
        api = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token"
        data = {"pwd_id": pwd_id, "passcode": password}
        async with httpx.AsyncClient() as client:
            timeout = httpx.Timeout(60.0, connect=60.0)
            response = await client.post(api, json=data, params=params, headers=self.headers, timeout=timeout)
            json_data = response.json()
            if json_data['status'] == 200 and json_data['data']:
                stoken = json_data["data"]["stoken"]
            else:
                stoken = ''
                custom_print(f"Transfer berkas gagal，{json_data['message']}")
            return stoken

    async def get_detail(self, pwd_id: str, stoken: str, pdir_fid: str = '0') -> str | tuple | None:
        api = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail"
        page = 1
        file_list: list[dict[str, Union[int, str]]] = []

        async with httpx.AsyncClient() as client:
            while True:
                params = {
                    'pr': 'ucpro',
                    'fr': 'pc',
                    'uc_param_str': '',
                    "pwd_id": pwd_id,
                    "stoken": stoken,
                    'pdir_fid': pdir_fid,
                    'force': '0',
                    "_page": str(page),
                    '_size': '50',
                    '_sort': 'file_type:asc,updated_at:desc',
                    '__dt': random.randint(200, 9999),
                    '__t': get_timestamp(13),
                }

                timeout = httpx.Timeout(60.0, connect=60.0)
                response = await client.get(api, headers=self.headers, params=params, timeout=timeout)
                json_data = response.json()

                is_owner = json_data['data']['is_owner']
                _total = json_data['metadata']['_total']
                if _total < 1:
                    return is_owner, file_list

                _size = json_data['metadata']['_size']  # Jumlah halaman per halaman
                _count = json_data['metadata']['_count']  # Jumlah halaman saat ini

                _list = json_data["data"]["list"]

                for file in _list:
                    d: dict[str, Union[int, str]] = {
                        "fid": file["fid"],
                        "file_name": file["file_name"],
                        "file_type": file["file_type"],
                        "dir": file["dir"],
                        "pdir_fid": file["pdir_fid"],
                        "include_items": file.get("include_items", ''),
                        "share_fid_token": file["share_fid_token"],
                        "status": file["status"]
                    }
                    file_list.append(d)
                if _total <= _size or _count < _size:
                    return is_owner, file_list

                page += 1

    async def get_sorted_file_list(self, pdir_fid='0', page='1', size='100', fetch_total='false',
                                   sort='') -> dict[str, Any]:
        params = {
            'pr': 'ucpro',
            'fr': 'pc',
            'uc_param_str': '',
            'pdir_fid': pdir_fid,
            '_page': page,
            '_size': size,
            '_fetch_total': fetch_total,
            '_fetch_sub_dirs': '1',
            '_sort': sort,
            '__dt': random.randint(100, 9999),
            '__t': get_timestamp(13),
        }

        async with httpx.AsyncClient() as client:
            timeout = httpx.Timeout(60.0, connect=60.0)
            response = await client.get('https://drive-pc.quark.cn/1/clouddrive/file/sort', params=params,
                                        headers=self.headers, timeout=timeout)
            json_data = response.json()
            return json_data

    async def get_user_info(self) -> str:

        params = {
            'fr': 'pc',
            'platform': 'pc',
        }

        async with httpx.AsyncClient() as client:
            timeout = httpx.Timeout(60.0, connect=60.0)
            response = await client.get('https://pan.quark.cn/account/info', params=params,
                                        headers=self.headers, timeout=timeout)
            json_data = response.json()
            if json_data['data']:
                nickname = json_data['data']['nickname']
                return nickname
            else:
                input("Login gagal! Silakan jalankan program ini lagi dan kemudian masuk ke akun Quark Anda di browser pop-up.")
                with open(f'{CONFIG_DIR}/cookies.txt', 'w', encoding='utf-8'):
                    sys.exit(-1)

    async def create_dir(self, pdir_name='Folder Baru') -> None:
        params = {
            'pr': 'ucpro',
            'fr': 'pc',
            'uc_param_str': '',
            '__dt': random.randint(100, 9999),
            '__t': get_timestamp(13),
        }

        json_data = {
            'pdir_fid': '0',
            'file_name': pdir_name,
            'dir_path': '',
            'dir_init_lock': False,
        }

        async with httpx.AsyncClient() as client:
            timeout = httpx.Timeout(60.0, connect=60.0)
            response = await client.post('https://drive-pc.quark.cn/1/clouddrive/file', params=params,
                                         json=json_data, headers=self.headers, timeout=timeout)
            json_data = response.json()
            if json_data["code"] == 0:
                custom_print(f'Direktori akar {pdir_name} Folder berhasil dibuat.！')
                new_config = {'user': self.user, 'pdir_id': json_data["data"]["fid"], 'dir_name': pdir_name}
                save_config(f'{CONFIG_DIR}/config.json', content=json.dumps(new_config, ensure_ascii=False))
                global to_dir_id
                to_dir_id = json_data["data"]["fid"]
                custom_print(f"Secara otomatis mengganti direktori penyimpanan ke {pdir_name} Map")
            elif json_data["code"] == 23008:
                custom_print('Terjadi konflik nama folder, silakan coba lagi setelah mengubah nama folder.', error_msg=True)
            else:
                custom_print(f"pesan kesalahan：{json_data['message']}", error_msg=True)

    async def run(self, input_line: str, folder_id: Union[str, None] = None, download: bool = False) -> None:
        self.folder_id = folder_id
        share_url = input_line.strip()
        custom_print(f'Tautan berbagi file：{share_url}')
        match_password = re.search("pwd=(.*?)(?=$|&)", share_url)
        password = match_password.group(1) if match_password else ""
        pwd_id = self.get_pwd_id(input_line).split("#")[0]
        if not pwd_id:
            custom_print('Tautan berbagi file tidak boleh kosong.！', error_msg=True)
            return
        stoken = await self.get_stoken(pwd_id, password)
        if not stoken:
            return
        is_owner, data_list = await self.get_detail(pwd_id, stoken)
        files_count = 0
        folders_count = 0
        files_list: list[str] = []
        folders_list: list[str] = []
        folders_map = {}
        files_id_list = []
        file_fid_list = []

        if data_list:
            total_files_count = len(data_list)
            for data in data_list:
                if data['dir']:
                    folders_count += 1
                    folders_list.append(data["file_name"])
                    folders_map[data["fid"]] = {
                        "file_name": data["file_name"],
                        "pdir_fid": data["pdir_fid"]
                    }
                else:
                    files_count += 1
                    files_list.append(data["file_name"])
                    files_id_list.append((data["fid"], data["file_name"]))

            custom_print(f'Jumlah total transfer：{total_files_count}，Jumlah file：{files_count}，Jumlah folder：{folders_count} | Mendukung penestingan')
            custom_print(f'Daftar Transfer File：{files_list}')
            custom_print(f'Daftar Transfer Folder：{folders_list}')

            fid_list = [i["fid"] for i in data_list]
            share_fid_token_list = [i["share_fid_token"] for i in data_list]

            if not self.folder_id:
                custom_print('ID direktori yang tersimpan tidak valid. Silakan ambil kembali. Jika Anda tidak dapat mengambilnya, silakan masukkan 0 sebagai ID folder.')
                return

            if download:
                if is_owner == 0:
                    custom_print(
                        'File yang akan diunduh harus berada di penyimpanan cloud Anda sendiri. Silakan transfer file tersebut ke penyimpanan cloud Anda terlebih dahulu, lalu dapatkan tautan berbagi dari penyimpanan cloud Anda untuk mengunduhnya.')
                    return

                for i in data_list:
                    if i['dir']:
                        data_list2 = [i]
                        not_dir = False
                        while True:
                            data_list3 = []
                            for i2 in data_list2:
                                custom_print(f'Mulai mengunduh：{i2["file_name"]} Di dalam folder{i2["include_items"]}berkas')
                                is_owner, file_data_list = await self.get_detail(pwd_id, stoken, pdir_fid=i2['fid'])

                                # record folder's fid start
                                if file_data_list:
                                    for data in file_data_list:
                                        if data['dir']:
                                            folders_map[data["fid"]] = {
                                                "file_name": data["file_name"],
                                                "pdir_fid": data["pdir_fid"]
                                            }

                                # record folder's fid stop
                                folder = i["file_name"]
                                fid_list = [i["fid"] for i in file_data_list]
                                await self.quark_file_download(fid_list, folder=folder, folders_map=folders_map)
                                file_fid_list.extend([i for i in file_data_list if not i2['dir']])
                                dir_list = [i for i in file_data_list if i['dir']]

                                if not dir_list:
                                    not_dir = True
                                data_list3.extend(dir_list)
                            data_list2 = data_list3
                            if not data_list2 or not_dir:
                                break

                if len(files_id_list) > 0 or len(file_fid_list) > 0:
                    fid_list = [i[0] for i in files_id_list]
                    file_fid_list.extend(fid_list)
                    await self.quark_file_download(file_fid_list, folder='.', folders_map=folders_map)

            else:
                if is_owner == 1:
                    custom_print('File tersebut sudah ada di penyimpanan cloud; tidak perlu mentransfernya lagi.')
                    return
                task_id = await self.get_share_save_task_id(pwd_id, stoken, fid_list, share_fid_token_list,
                                                            to_pdir_fid=self.folder_id)
                await self.submit_task(task_id)
            print()

    async def get_share_save_task_id(self, pwd_id: str, stoken: str, first_ids: list[str], share_fid_tokens: list[str],
                                     to_pdir_fid: str = '0') -> str:
        task_url = "https://drive.quark.cn/1/clouddrive/share/sharepage/save"
        params = {
            "pr": "ucpro",
            "fr": "pc",
            "uc_param_str": "",
            "__dt": random.randint(600, 9999),
            "__t": get_timestamp(13),
        }
        data = {"fid_list": first_ids,
                "fid_token_list": share_fid_tokens,
                "to_pdir_fid": to_pdir_fid, "pwd_id": pwd_id,
                "stoken": stoken, "pdir_fid": "0", "scene": "link"}

        async with httpx.AsyncClient() as client:
            timeout = httpx.Timeout(60.0, connect=60.0)
            response = await client.post(task_url, json=data, headers=self.headers, params=params, timeout=timeout)
            json_data = response.json()
            task_id = json_data['data']['task_id']
            custom_print(f'Dapatkan Task ID：{task_id}')
            return task_id

    @staticmethod
    async def download_file(download_url: str, save_path: str, headers: dict) -> None:
        async with httpx.AsyncClient() as client:
            timeout = httpx.Timeout(60.0, connect=60.0)
            async with client.stream("GET", download_url, headers=headers, timeout=timeout) as response:
                if response.headers.get("content-length") is None:
                    response.headers["content-length"] = "0"
                with open(save_path, "wb") as f:
                    with tqdm(unit="B", unit_scale=True,
                              desc=os.path.basename(save_path),
                              ncols=80) as pbar:
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
                            pbar.update(len(chunk))

    async def quark_file_download(self, fids: list[str], folder: str = '', folders_map=None) -> None:
        folders_map = folders_map or {}
        params = {
            'pr': 'ucpro',
            'fr': 'pc',
            'sys': 'win32',
            've': '2.5.56',
            'ut': '',
            'guid': '',
        }

        data = {
            'fids': fids
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0",

            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "accept-language": "zh-CN",
            "origin": "https://pan.quark.cn",
            "referer": "https://pan.quark.cn/",
            "cookie": self.cookies
        }

        download_api = 'https://drive-pc.quark.cn/1/clouddrive/file/download'

        for _ in range(2):
            async with httpx.AsyncClient() as client:
                timeout = httpx.Timeout(60.0, connect=60.0)
                response = await client.post(download_api, json=data, headers=headers, params=params, timeout=timeout)
                json_data = response.json()

                if json_data.get('code') == 23018:
                    headers['User-Agent'] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                             "(KHTML, like Gecko) quark-cloud-drive/2.5.56 Chrome/100.0.4896.160 "
                                             "Electron/18.3.5.12-a038f7b798 Safari/537.36 Channel/pckk_other_ch")
                    continue

                data_list = json_data.get('data', None)
                if json_data['status'] != 200:
                    custom_print(f"agal mengambil daftar alamat unduhan file., {json_data['message']}", error_msg=True)
                    return
                elif data_list:
                    custom_print('Daftar alamat unduhan file berhasil diambil.')

                save_folder = 'downloads'  # if folder else 'downloads'
                os.makedirs(save_folder, exist_ok=True)
                n = 0
                for i in data_list:
                    n += 1
                    filename = i["file_name"]
                    custom_print(f'Mulai mengunduh yang pertama{n}berkas-{filename}')

                    # build save path start
                    base_path = ""
                    if "pdir_fid" in i:
                        pdir_fid = i["pdir_fid"]
                        while pdir_fid in folders_map:
                            base_path = "/" + folders_map[pdir_fid]["file_name"] + base_path
                            pdir_fid = folders_map[pdir_fid]["pdir_fid"]
                    final_save_folder = f"{save_folder}/{base_path}"
                    os.makedirs(final_save_folder, exist_ok=True)
                    # build save path stop

                    download_url = i["download_url"]
                    save_path = os.path.join(final_save_folder, filename)
                    headers = {
                        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, "
                                      "like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0",
                        "origin": "https://pan.quark.cn",
                        "referer": "https://pan.quark.cn/",
                        "cookie": self.cookies
                    }
                    await self.download_file(download_url, save_path, headers=headers)
            return

    async def submit_task(self, task_id: str, retry: int = 50) -> bool | dict:

        for i in range(retry):
            await asyncio.sleep(random.randint(500, 1000) / 1000)
            custom_print(f'TIDAK{i + 1}Kirim tugas')
            submit_url = (f"https://drive-pc.quark.cn/1/clouddrive/task?pr=ucpro&fr=pc&uc_param_str=&task_id={task_id}"
                          f"&retry_index={i}&__dt=21192&__t={get_timestamp(13)}")

            async with httpx.AsyncClient() as client:
                timeout = httpx.Timeout(60.0, connect=60.0)
                response = await client.get(submit_url, headers=self.headers, timeout=timeout)
                json_data = response.json()

            if json_data['message'] == 'ok':
                if json_data['data']['status'] == 2:
                    if 'to_pdir_name' in json_data['data']['save_as']:
                        folder_name = json_data['data']['save_as']['to_pdir_name']
                    else:
                        folder_name = ' direktori akar'
                    if json_data['data']['task_title'] == 'Bagikan - Simpan':
                        custom_print(f"Akhir dari Task ID：{task_id}")
                        custom_print(f'Lokasi penyimpanan file：{folder_name} Map')
                    return json_data
            else:
                if json_data['code'] == 32003 and 'capacity limit' in json_data['message']:
                    custom_print("Transfer gagal, ruang penyimpanan cloud tidak mencukupi! Harap perhatikan jumlah item yang sudah berhasil disimpan untuk menghindari penyimpanan ganda.", error_msg=True)
                elif json_data['code'] == 41013:
                    custom_print(f"”{to_dir_name}“ Folder penyimpanan cloud tidak ada. Silakan jalankan program lagi, tekan 3 untuk mengubah direktori penyimpanan, dan coba lagi!", error_msg=True)
                else:
                    custom_print(f"pesan kesalahan：{json_data['message']}", error_msg=True)
                input(f'[{get_datetime()}] Program tersebut telah berakhir.')
                sys.exit()

    def init_config(self, _user, _pdir_id, _dir_name):
        try:
            os.makedirs('share', exist_ok=True)
            json_data = read_config(f'{CONFIG_DIR}/config.json', 'json')
            if json_data:
                user = json_data.get('user', 'jack')
                if user != _user:
                    _pdir_id = '0'
                    _dir_name = 'direktori akar'
                    new_config = {'user': _user, 'pdir_id': _pdir_id, 'dir_name': _dir_name}
                    save_config(f'{CONFIG_DIR}/config.json', content=json.dumps(new_config, ensure_ascii=False))
                else:
                    _pdir_id = json_data.get('pdir_id', '0')
                    _dir_name = json_data.get('dir_name', 'direktori akar')
        except (json.decoder.JSONDecodeError, FileNotFoundError):
            new_config = {'user': self.user, 'pdir_id': self.pdir_id, 'dir_name': self.dir_name}
            save_config(f'{CONFIG_DIR}/config.json', content=json.dumps(new_config, ensure_ascii=False))
        return _user, _pdir_id, _dir_name

    async def load_folder_id(self, renew=False) -> Union[tuple, None]:

        self.user = await self.get_user_info()
        self.user, self.pdir_id, self.dir_name = self.init_config(self.user, self.pdir_id, self.dir_name)
        if not renew:
            custom_print(f'nama belakang：{self.user}')
            custom_print(f'Direktori penyimpanan cloud Anda saat ini: {self.dir_name} Map')

        if renew:
            pdir_id = input(f'[{get_datetime()}] Silakan masukkan ID folder untuk lokasi penyimpanan (boleh kosong): ')
            if pdir_id == '0':
                self.dir_name = 'direktori akar'
                new_config = {'user': self.user, 'pdir_id': self.pdir_id, 'dir_name': self.dir_name}
                save_config(f'{CONFIG_DIR}/config.json', content=json.dumps(new_config, ensure_ascii=False))

            elif len(pdir_id) < 32:
                file_list_data = await self.get_sorted_file_list()
                fd_list = file_list_data['data']['list']
                fd_list = [{i['fid']: i['file_name']} for i in fd_list if i.get('dir')]
                if fd_list:
                    table = PrettyTable(['Nomor seri', 'ID Folder', 'Nama Folder'])
                    for idx, item in enumerate(fd_list, 1):
                        key, value = next(iter(item.items()))
                        table.add_row([idx, key, value])
                    print(table)
                    num = input(f'[{get_datetime()}] Silakan pilih lokasi tempat Anda ingin menyimpan (masukkan nomor yang sesuai). : ')
                    if not num or int(num) > len(fd_list):
                        custom_print('Nomor seri yang dimasukkan tidak ada; peralihan direktori penyimpanan gagal.', error_msg=True)
                        json_data = read_config(f'{CONFIG_DIR}/config.json', 'json')
                        return json_data['pdir_id'], json_data['dir_name']

                    item = fd_list[int(num) - 1]
                    self.pdir_id, self.dir_name = next(iter(item.items()))
                    new_config = {'user': self.user, 'pdir_id': self.pdir_id, 'dir_name': self.dir_name}
                    save_config(f'{CONFIG_DIR}/config.json', content=json.dumps(new_config, ensure_ascii=False))

        return self.pdir_id, self.dir_name

    async def get_share_task_id(self, fid: str, file_name: str, url_type: int = 1, expired_type: int = 2,
                                password: str = '') -> str:

        json_data = {
            "fid_list": [
                fid
            ],
            "title": file_name,

            "url_type": url_type,
            "expired_type": expired_type
        }
        if url_type == 2:
            if password:
                json_data["passcode"] = password
            else:
                json_data["passcode"] = generate_random_code()

        params = {
            'pr': 'ucpro',
            'fr': 'pc',
            'uc_param_str': '',
        }

        async with httpx.AsyncClient() as client:
            timeout = httpx.Timeout(60.0, connect=60.0)
            response = await client.post('https://drive-pc.quark.cn/1/clouddrive/share', params=params,
                                         json=json_data, headers=self.headers, timeout=timeout)
            json_data = response.json()
            return json_data['data']['task_id']

    async def get_share_id(self, task_id: str) -> str:
        params = {
            'pr': 'ucpro',
            'fr': 'pc',
            'uc_param_str': '',
            'task_id': task_id,
            'retry_index': '0',
        }
        async with httpx.AsyncClient() as client:
            timeout = httpx.Timeout(60.0, connect=60.0)
            response = await client.get('https://drive-pc.quark.cn/1/clouddrive/task', params=params,
                                        headers=self.headers, timeout=timeout)
            json_data = response.json()
            return json_data['data']['share_id']

    async def submit_share(self, share_id: str) -> tuple:
        params = {
            'pr': 'ucpro',
            'fr': 'pc',
            'uc_param_str': '',
        }

        json_data = {
            'share_id': share_id,
        }
        async with httpx.AsyncClient() as client:
            timeout = httpx.Timeout(60.0, connect=60.0)
            response = await client.post('https://drive-pc.quark.cn/1/clouddrive/share/password', params=params,
                                         json=json_data, headers=self.headers, timeout=timeout)
            json_data = response.json()
            share_url = json_data['data']['share_url']
            title = json_data['data']['title']
            if 'passcode' in json_data['data']:
                share_url = share_url + f"?pwd={json_data['data']['passcode']}"
            return share_url, title

    async def share_run(self, share_url: str, folder_id: Union[str, None] = None, url_type: int = 1,
                        expired_type: int = 2, password: str = '', traverse_depth: int = 2) -> None:
        first_dir = ''
        second_dir = ''
        try:
            self.folder_id = folder_id
            custom_print(f'Alamat web folder：{share_url}')
            pwd_id = share_url.rsplit('/', maxsplit=1)[1].split('-')[0]

            first_page = 1
            n = 0
            error = 0
            os.makedirs('share', exist_ok=True)
            save_share_path = 'share/share_url.txt'

            safe_copy(save_share_path, 'share/share_url_backup.txt')
            with open(save_share_path, 'w', encoding='utf-8'):
                pass

            # 如果遍历深度为0，直接分享根目录
            if traverse_depth == 0:
                try:
                    custom_print('Mulai berbagi semua direktori root di halaman tersebut.')
                    task_id = await self.get_share_task_id(pwd_id, "direktori akar", url_type=url_type,
                                                           expired_type=expired_type,
                                                           password=password)
                    share_id = await self.get_share_id(task_id)
                    share_url, title = await self.submit_share(share_id)
                    with open(save_share_path, 'a', encoding='utf-8') as f:
                        content = f'1 | {title} | {share_url}'
                        f.write(content + '\n')
                        custom_print(f'membagikan {title} berhasil')
                    return
                except Exception as e:
                    print('分享失败：', e)
                    return

            while True:
                json_data = await self.get_sorted_file_list(pwd_id, page=str(first_page), size='50', fetch_total='1',
                                                            sort='file_type:asc,file_name:asc')
                for i1 in json_data['data']['list']:
                    if i1['dir']:
                        first_dir = i1['file_name']
                        # 如果遍历深度为1，直接分享一级目录
                        if traverse_depth == 1:
                            n += 1
                            share_success = False
                            share_error_msg = ''
                            fid = ''
                            for i in range(3):
                                try:
                                    custom_print(f'{n}.Mulai berbagi {first_dir} Map')
                                    random_time = random.choice([0.5, 1, 1.5, 2])
                                    await asyncio.sleep(random_time)
                                    fid = i1['fid']
                                    task_id = await self.get_share_task_id(fid, first_dir, url_type=url_type,
                                                                           expired_type=expired_type,
                                                                           password=password)
                                    share_id = await self.get_share_id(task_id)
                                    share_url, title = await self.submit_share(share_id)
                                    with open(save_share_path, 'a', encoding='utf-8') as f:
                                        content = f'{n} | {first_dir} | {share_url}'
                                        f.write(content + '\n')
                                        custom_print(f'{n}.Berhasil dibagikan {first_dir} Map')
                                        share_success = True
                                        break
                                except Exception as e:
                                    share_error_msg = e
                                    error += 1

                            if not share_success:
                                print('Berbagi gagal：', share_error_msg)
                                save_config('./share/share_error.txt',
                                            content=f'{error}.{first_dir} 文件夹\n', mode='a')
                                save_config('./share/retry.txt',
                                            content=f'{n} | {first_dir} | {fid}\n', mode='a')
                            continue

                        # 遍历深度为2，遍历二级目录
                        second_page = 1
                        while True:
                            # print(f'正在获取{first_dir}第{first_page}页，二级目录第{second_page}页，目前共分享{n}文件')
                            json_data2 = await self.get_sorted_file_list(i1['fid'], page=str(second_page),
                                                                         size='50', fetch_total='1',
                                                                         sort='file_type:asc,file_name:asc')
                            for i2 in json_data2['data']['list']:
                                if i2['dir']:
                                    n += 1
                                    share_success = False
                                    share_error_msg = ''
                                    fid = ''
                                    for i in range(3):
                                        try:
                                            second_dir = i2['file_name']
                                            custom_print(f'{n}.开始分享 {first_dir}/{second_dir} 文件夹')
                                            random_time = random.choice([0.5, 1, 1.5, 2])
                                            await asyncio.sleep(random_time)
                                            # print('获取到文件夹ID：', i2['fid'])
                                            fid = i2['fid']
                                            task_id = await self.get_share_task_id(fid, second_dir, url_type=url_type,
                                                                                   expired_type=expired_type,
                                                                                   password=password)
                                            share_id = await self.get_share_id(task_id)
                                            share_url, title = await self.submit_share(share_id)
                                            with open(save_share_path, 'a', encoding='utf-8') as f:
                                                content = f'{n} | {first_dir} | {second_dir} | {share_url}'
                                                f.write(content + '\n')
                                                custom_print(f'{n}.Berhasil dibagikan {first_dir}/{second_dir} Map')
                                                share_success = True
                                                break

                                        except Exception as e:
                                            share_error_msg = e
                                            error += 1

                                    if not share_success:
                                        print('Berbagi gagal：', share_error_msg)
                                        save_config('./share/share_error.txt',
                                                    content=f'{error}.{first_dir}/{second_dir} Map\n', mode='a')
                                        save_config('./share/retry.txt',
                                                    content=f'{n} | {first_dir} | {second_dir} | {fid}\n', mode='a')
                            second_total = json_data2['metadata']['_total']
                            second_size = json_data2['metadata']['_size']
                            second_page = json_data2['metadata']['_page']
                            if second_size * second_page >= second_total:
                                break
                            second_page += 1

                second_total = json_data['metadata']['_total']
                second_size = json_data['metadata']['_size']
                second_page = json_data['metadata']['_page']
                if second_size * second_page >= second_total:
                    break
                first_page += 1
            custom_print(f"Sebanyak {n} Folder，Disimpan ke {save_share_path}")

        except Exception as e:
            print('Berbagi gagal：', e)
            with open('./share/share_error.txt', 'a', encoding='utf-8') as f:
                f.write(f'{first_dir}/{second_dir} Map')

    async def share_run_retry(self, retry_url: str, url_type: int = 1, expired_type: int = 2, password: str = ''):

        data_list = retry_url.split('\n')
        n = 0
        error = 0
        save_share_path = 'share/retry_share_url.txt'
        error_data = []
        for i1 in data_list:
            data = i1.split(' | ')
            if data and len(data) == 4:
                first_dir = data[-3]
                second_dir = data[-2]
                fid = data[-1]
                share_error_msg = ''
                for i in range(3):
                    try:
                        task_id = await self.get_share_task_id(fid, second_dir, url_type=url_type,
                                                               expired_type=expired_type,
                                                               password=password)
                        share_id = await self.get_share_id(task_id)
                        share_url, title = await self.submit_share(share_id)
                        with open(save_share_path, 'a', encoding='utf-8') as f:
                            content = f'{n} | {first_dir} | {second_dir} | {share_url}'
                            f.write(content + '\n')
                            custom_print(f'{n}.Berhasil dibagikan {first_dir}/{second_dir} Map')
                            share_success = True
                            break
                    except Exception as e:
                        share_error_msg = e
                        error += 1

                if not share_success:
                    print('Berbagi gagal：', share_error_msg)
                    error_data.append(i1)
        error_content = '\n'.join(error_data)
        save_config(path='./share/retry.txt', content=error_content, mode='w')


def load_url_file(fpath: str) -> list[str]:
    url_pattern = re.compile(r'https?://\S+')

    with open(fpath, encoding='utf-8') as f:
        content = f.read()

    return url_pattern.findall(content)


def print_ascii():
    print(r"""
║                                     _                                  _                     _       ║    
║       __ _   _   _    __ _   _ __  | | __    _ __     __ _   _ __     | |_    ___     ___   | |      ║
║      / _  | | | | |  / _  | | '__| | |/ /   | '_ \   / _  | |  _ \    | __|  / _ \   / _ \  | |      ║
║     | (_| | | |_| | | (_| | | |    |   <    | |_) | | (_| | | | | |   | |_  | (_) | | (_) | | |      ║
║      \__, |  \__,_|  \__,_| |_|    |_|\_\   | .__/   \__,_| |_| |_|    \__|  \___/   \___/  |_|      ║
║         |_|                                 |_|                                                      ║""".strip())


def print_menu() -> None:
    print("╔══════════════════════════════════════════════════════════════════════════════════════════════════════╗")
    print_ascii()
    print("║                                                                                                      ║")
    print("║                                  Author: Hmily  Version: 0.0.6                                       ║")
    print("║                          GitHub: https://github.com/ihmily/QuarkPanTool                              ║")
    print("╠══════════════════════════════════════════════════════════════════════════════════════════════════════╣")
    print("║     1.Bagikan alamat untuk menyimpan file.                                                           ║")
    print("║     2.Buat tautan berbagi secara massal.                                                             ║")
    print("║     3.Beralih ke direktori penyimpanan cloud drive.                                                  ║")
    print("║     4.Buat folder penyimpanan cloud.                                                                 ║")
    print("║     5.Unduh ke lokal                                                                                 ║")
    print("║     6.Masuk                                                                                          ║")
    print("╚══════════════════════════════════════════════════════════════════════════════════════════════════════╝")


if __name__ == '__main__':
    quark_file_manager = QuarkPanFileManager(headless=False, slow_mo=500)
    while True:
        print_menu()

        to_dir_id, to_dir_name = asyncio.run(quark_file_manager.load_folder_id())

        input_text = input("Masukkan pilihan (1-6 atau q untuk keluar).：")

        if input_text and input_text.strip() in ['q', 'Q']:
            print("Program telah berakhir.！")
            sys.exit(0)

        if input_text and input_text.strip() in [str(i) for i in range(1, 7)]:
            if input_text.strip() == '1':
                save_option = input("Transfer massal?(1.Ya 2.Tidak)：")
                if save_option and save_option == '1':
                    try:
                        urls = load_url_file('./url.txt')
                        if not urls:
                            custom_print('\nAlamat berbagi kosong! Silakan masukkan alamat berbagi (satu alamat per baris) di file url.txt terlebih dahulu.')
                            continue

                        custom_print(f"\rFile url.txt terdeteksi berisi{len(urls)}Bagikan tautan")
                        ok = input("Konfirmasi apakah Anda ingin memulai penyimpanan massal (tekan 2 untuk konfirmasi).:")
                        if ok and ok.strip() == '2':
                            for index, url in enumerate(urls):
                                print(f"Saat ini sedang mentransfer yang pertama...{index + 1}个")
                                asyncio.run(quark_file_manager.run(url.strip(), to_dir_id))
                    except FileNotFoundError:
                        with open('url.txt', 'w', encoding='utf-8'):
                            sys.exit(-1)
                else:
                    url = input("Silakan masukkan alamat berbagi file Quark.：")
                    if url and len(url.strip()) > 20:
                        asyncio.run(quark_file_manager.run(url.strip(), to_dir_id))

            elif input_text.strip() == '2':
                share_option = input("Silakan masukkan pilihan Anda (1 Bagikan 2 Coba lagi berbagi)：")
                if share_option and share_option == '1':
                    url = input("Silakan masukkan alamat halaman web dari folder yang ingin Anda bagikan.：")
                    if not url or len(url.strip()) < 20:
                        continue
                else:
                    try:
                        url = read_config(path='./share/retry.txt', mode='r')
                        if not url:
                            print('\nretry.txt Kosong! Silakan periksa file tersebut.')
                            continue
                    except FileNotFoundError:
                        save_config('./share/retry.txt', content='')
                        print('\nshare/retry.txt Berkas tersebut kosong.！')
                        continue

                expired_option = {"1": 2, "2": 3, "3": 4, "4": 1}
                print("1. 1 hari 2. 7 hari 3. 30 hari 4. Permanen")
                select_option = input("Silakan masukkan opsi durasi berbagi.：")
                _expired_type = expired_option.get(select_option, 4)
                is_private = input("Enkripsi diperlukan (1 Tidak / 2 Ya)：")
                url_encrypt = 2 if is_private == '2' else 1
                passcode = input('Silakan masukkan kode ekstraksi berbagi yang ingin Anda atur (cukup tekan Enter, kode dapat dihasilkan secara acak).:') if url_encrypt == 2 else ''

                print("\n\rSilakan pilih kedalaman penelusuran：")
                print("0.Jangan melakukan traverse (hanya berbagi direktori root - default) ")
                print("1.Penelusuran hanya berbagi direktori tingkat pertama.")
                print("2.遍历只分享两级目录\n")
                traverse_option = input("Silakan masukkan pilihan Anda (0/1/2)：")
                _traverse_depth = 0  # 默认只分享根目录
                if traverse_option in ['1', '2']:
                    _traverse_depth = int(traverse_option)

                if share_option and share_option == '1':
                    asyncio.run(quark_file_manager.share_run(
                        url.strip(), folder_id=to_dir_id, url_type=int(url_encrypt),
                        expired_type=int(_expired_type), password=passcode, traverse_depth=_traverse_depth))
                else:
                    asyncio.run(quark_file_manager.share_run_retry(url.strip(), url_type=url_encrypt,
                                                                   expired_type=_expired_type, password=passcode))

            elif input_text.strip() == '3':
                to_dir_id, to_dir_name = asyncio.run(quark_file_manager.load_folder_id(renew=True))
                custom_print(f"Direktori penyimpanan telah diubah ke penyimpanan cloud. {to_dir_name} Map\n")

            elif input_text.strip() == '4':
                create_name = input("Silakan masukkan nama folder yang ingin Anda buat.：")
                if create_name:
                    asyncio.run(quark_file_manager.create_dir(create_name.strip()))
                else:
                    custom_print("Nama folder yang Anda buat tidak boleh kosong!", error_msg=True)

            elif input_text.strip() == '5':
                try:
                    is_batch = input("Masukkan pilihan Anda (1. Unduh dari satu alamat, 2. Unduh secara bertahap):")
                    if is_batch:
                        if is_batch.strip() == '1':
                            url = input("Silakan masukkan alamat berbagi file Quark.：")
                            asyncio.run(quark_file_manager.run(url.strip(), to_dir_id, download=True))
                        elif is_batch.strip() == '2':
                            urls = load_url_file('./url.txt')
                            if not urls:
                                print('\nAlamat berbagi kosong! Silakan masukkan alamat berbagi (satu alamat per baris) di file url.txt terlebih dahulu.')
                                continue

                            for index, url in enumerate(urls):
                                asyncio.run(quark_file_manager.run(url.strip(), to_dir_id, download=True))

                except FileNotFoundError:
                    with open('url.txt', 'w', encoding='utf-8'):
                        sys.exit(-1)

            elif input_text.strip() == '6':
                save_config(f'{CONFIG_DIR}/cookies.txt', '')
                quark_file_manager = QuarkPanFileManager(headless=False, slow_mo=500)
                quark_file_manager.get_cookies()

        else:
            custom_print("Masukan tidak valid, harap masukkan kembali.")
