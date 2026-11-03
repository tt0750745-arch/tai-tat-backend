"""Isolated downloader. No login cookies; public IP connections only."""
import sys, socket, ipaddress, resource
from pathlib import Path

# yt-dlp network calls are checked at the actual socket connection.
connect_original=socket.socket.connect

def public_connect(sock,address):
    if sock.family in (socket.AF_INET,socket.AF_INET6):
        host,port=address[:2]
        addresses=socket.getaddrinfo(host,port,sock.family,sock.type)
        candidates=[]
        for family,kind,proto,canon,sockaddr in addresses:
            if not ipaddress.ip_address(sockaddr[0].split('%',1)[0]).is_global:
                raise OSError('Private network destinations are disabled')
            candidates.append(sockaddr)
        if not candidates:raise OSError('No public address')
        address=candidates[0]
    return connect_original(sock,address)

socket.socket.connect=public_connect
resource.setrlimit(resource.RLIMIT_FSIZE,(160*1024*1024,160*1024*1024))
resource.setrlimit(resource.RLIMIT_CPU,(150,160))
import yt_dlp
url,directory=sys.argv[1:3]

def size_guard(data):
    if data.get('downloaded_bytes',0)>50*1024*1024:raise yt_dlp.utils.DownloadError('File size limit')

options={
    'noplaylist':True,'max_downloads':1,'quiet':True,'no_warnings':True,'ignoreconfig':True,
    'cachedir':False,'socket_timeout':15,'retries':1,'fragment_retries':1,
    'concurrent_fragment_downloads':1,'hls_prefer_native':True,
    'format':'bv*[height<=720][ext=mp4]+ba[ext=m4a]/b*[height<=?720][ext=mp4]/b*[height<=?720]',
    'merge_output_format':'mp4','max_filesize':50*1024*1024,
    'outtmpl':str(Path(directory)/'tai-tat.%(ext)s'),'restrictfilenames':True,
    'match_filter':yt_dlp.utils.match_filter_func('!is_live & duration <=? 600'),
    'progress_hooks':[size_guard],'js_runtimes':{'node':{}},
    'postprocessor_args':{'ffmpeg_i':['-protocol_whitelist','file,pipe,crypto']},
}
with yt_dlp.YoutubeDL(options) as downloader:downloader.download([url])
