"""Small authenticated yt-dlp job service. Temporary files, one job at a time."""
import concurrent.futures, hmac, json, os, secrets, shutil, subprocess, sys, tempfile, threading, time, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

MAX_BYTES = 50 * 1024 * 1024
TTL = 900
ROOT = Path(tempfile.mkdtemp(prefix='tai-tat-'))
JOBS = {}
LOCK = threading.RLock()
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=1)
HOSTS = {'interactive-examples.mdn.mozilla.net','youtube.com','youtu.be','tiktok.com','facebook.com','fb.watch','instagram.com','twitter.com','x.com','vimeo.com','reddit.com','redd.it','pinterest.com','pin.it','douyin.com','iesdouyin.com','xiaohongshu.com','xhslink.com'}


def validate_url(raw):
    if not isinstance(raw,str) or len(raw)>8192:
        raise ValueError('Link không hợp lệ.')
    u=urlsplit(raw)
    host=(u.hostname or '').lower()
    if u.scheme not in ('http','https') or u.username or u.password or u.port not in (None,80,443):
        raise ValueError('Link không hợp lệ.')
    if not any(host==h or host.endswith('.'+h) for h in HOSTS):
        raise ValueError('Nguồn này chưa được bật trên máy chủ.')
    return raw


def cleanup():
    with LOCK:
        for key,j in list(JOBS.items()):
            if time.time()-j['created']>TTL and j['state'] not in ('queued','running'):
                shutil.rmtree(ROOT/key,ignore_errors=True)
                del JOBS[key]


def run_job(key, url):
    with LOCK: JOBS[key]['state']='running'
    dest=ROOT/key
    dest.mkdir(mode=0o700)
    try:
        # An isolated process controls time, outbound destinations and file limits.
        error_log=(dest/'.error.log').open('wb')
        proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('runner.py')),url,str(dest)],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=error_log,
            env={k:v for k,v in os.environ.items() if k not in ('API_KEY',)},start_new_session=True)
        try:
            until=time.monotonic()+180
            while proc.poll() is None:
                size=sum(f.stat().st_size for f in dest.rglob('*') if f.is_file())
                if size>MAX_BYTES*3 or time.monotonic()>until:
                    raise TimeoutError('limit')
                time.sleep(.3)
            if proc.returncode!=0:
                error_log.close()
                error_text=(dest/'.error.log').read_text(errors='replace')[-1500:]
                error_text=re.sub(r'https?://\S+','[url]',error_text)
                print('download_error:',error_text,flush=True)
                raise RuntimeError('download')
        finally:
            if proc.poll() is None:
                import signal
                os.killpg(proc.pid,signal.SIGKILL)
                proc.wait()
            error_log.close()
        files=[p for p in dest.iterdir() if p.is_file() and p.suffix.lower() in ('.mp4','.webm','.mkv','.mov','.mp3','.m4a','.jpg','.png','.webp')]
        if len(files)!=1 or files[0].stat().st_size>MAX_BYTES: raise RuntimeError('file')
        probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(files[0])],capture_output=True,text=True,timeout=15)
        if probe.returncode!=0 or float(probe.stdout.strip())>600: raise RuntimeError('duration')
        with LOCK: JOBS[key].update(state='done',file=str(files[0]),name=files[0].name,size=files[0].stat().st_size)
    except Exception:
        shutil.rmtree(dest,ignore_errors=True)
        with LOCK: JOBS[key].update(state='error',error='Không tải được. Nguồn có thể chặn IP máy chủ, cần đăng nhập, hoặc file vượt 50 MB / 10 phút.')


def create_job(url):
    validate_url(url)
    cleanup()
    with LOCK:
        if any(j['state'] in ('queued','running') for j in JOBS.values()):
            raise BlockingIOError('Máy chủ đang xử lý một file. Vui lòng đợi.')
        if len(JOBS)>=10: raise BlockingIOError('Đã đạt giới hạn file tạm. Thử lại sau 15 phút.')
        key=secrets.token_urlsafe(24)
        JOBS[key]={'created':time.time(),'state':'queued','ticket':secrets.token_urlsafe(32)}
        POOL.submit(run_job,key,url)
        return {'id':key,'ticket':JOBS[key]['ticket'],'state':'queued'}


class Handler(BaseHTTPRequestHandler):
    server_version='TaiTat/1.0'
    def log_message(self,*args): pass  # Do not log URLs, tickets or credentials.
    def respond(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    def authorized(self):
        key=os.getenv('API_KEY','')
        return len(key)>=32 and hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+key)
    def do_POST(self):
        if not self.authorized(): return self.respond({'error':'Không được phép truy cập.'},401)
        if self.path!='/jobs': return self.respond({'error':'Không tìm thấy.'},404)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>10000: raise ValueError('Yêu cầu quá lớn hoặc thiếu nội dung.')
            data=json.loads(self.rfile.read(size))
            job=create_job(data.get('url'))
            self.respond(job,202)
        except BlockingIOError as e:self.respond({'error':str(e)},429)
        except (ValueError,TypeError,KeyError):self.respond({'error':'Link không hợp lệ hoặc nguồn chưa được bật.'},400)
    def do_GET(self):
        u=urlsplit(self.path)
        if u.path=='/health':return self.respond({'ok':True,'ready':len(os.getenv('API_KEY',''))>=32})
        if u.path.startswith('/jobs/') or u.path.startswith('/download/'):
            if not self.authorized():return self.respond({'error':'Không được phép truy cập.'},401)
            cleanup();key=u.path.rsplit('/',1)[-1]
            with LOCK:j=dict(JOBS.get(key,{}))
            if not j:return self.respond({'error':'File đã hết hạn hoặc máy chủ vừa khởi động lại.'},404)
            ticket=parse_qs(u.query).get('ticket',[''])[0]
            if not hmac.compare_digest(j['ticket'],ticket):return self.respond({'error':'Không được phép truy cập.'},403)
            if u.path.startswith('/jobs/'):
                return self.respond({k:j[k] for k in ('state','error','name','size') if k in j})
            if j['state']!='done':return self.respond({'error':'File chưa sẵn sàng.'},409)
            f=Path(j['file'])
            self.send_response(200)
            mime={'.mp4':'video/mp4','.webm':'video/webm','.mkv':'video/x-matroska','.m4a':'audio/mp4','.mp3':'audio/mpeg'}.get(f.suffix,'application/octet-stream')
            self.send_header('Content-Type',mime);self.send_header('Content-Length',str(f.stat().st_size))
            self.send_header('Content-Disposition','attachment; filename="'+f.name+'"')
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
            try:
                with f.open('rb') as source:shutil.copyfileobj(source,self.wfile,256*1024)
            except (BrokenPipeError,ConnectionResetError):pass
            return
        self.respond({'error':'Không tìm thấy.'},404)


if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','10000'))),Handler).serve_forever()
