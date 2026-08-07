import gzip
import socket
import ssl
import sys
import time
import tkinter



WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100

origen = "file://local/index.html"
SOCKETS = {}
MAX_REDIRECTS = 10
CACHE = {}

#####################################
# FUNCTION UTILS
#####################################

def lex(body):
        text = ""
        in_tag = False
        for c in body:
            if c == "<":
                in_tag = True
            elif c == ">":
                in_tag = False
            elif not in_tag:
                text += c

        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&amp;", "&")
        text = text.replace("&quot;", '"')
        return text
 

#####################################
# BROWSER CLASS
#####################################

class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window, 
            width=WIDTH,
            height=HEIGHT
        )
        self.canvas.pack()
        self.display_list = []
        self.scroll = 0
        self.window.bind("<Down>", self.scrolldown)
        self.window.bind("<Up>", self.scrollup)

    def layout(self, text):
        self.display_list = []
        cursor_x, cursor_y = HSTEP, VSTEP
        for c in text:
            self.display_list.append((cursor_x, cursor_y, c))
            cursor_x += HSTEP
            if cursor_x >= WIDTH - HSTEP:
                cursor_y += VSTEP
                cursor_x = HSTEP
        return self.display_list     
    
    def draw(self):
        self.canvas.delete("all")
        for x, y, c in self.display_list:
            if y > self.scroll + HEIGHT: continue
            if y + VSTEP < self.scroll: continue
            self.canvas.create_text(x, y - self.scroll, text=c)

    def load(self, url):

        url_obj = URL(url)
        
        body = url_obj.request()
        if url_obj.view_source:
            text = body
        else:
            text = lex(body) 
        self.display_list = self.layout(text)   
        self.draw() 

    def scrolldown(self, e):
        self.scroll += SCROLL_STEP
        self.draw()  

    def scrollup(self, e):
            self.scroll -= SCROLL_STEP
            self.draw()      


#####################################
# URL CLASS
#####################################         

class URL:

    def __init__(self, url=origen):
        self.raw_url = url

        if url.startswith("view-source:"):
            self.view_source = True
            _, url = url.split("view-source:", 1)
        else:
            self.view_source = False

        if "://" in url:
            self.scheme, url = url.split("://", 1)
        else:
            self.scheme, url = url.split(":", 1)

        assert self.scheme in ["http", "https", "file", "data"]

        self.host = None
        self.port = None
        if self.scheme == "file" or self.scheme == "data":
            self.path = url
            return

        if "/" not in url:
            url = url + "/"
        self.host, url = url.split("/", 1)
        self.path = "/" + url

        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https":
            self.port = 443

        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

    def full_url(self):
        if self.scheme in ["file", "data"]:
            return f"{self.scheme}:{self.path}"
        return f"{self.scheme}://{self.host}:{self.port}{self.path}"

    def resolve_relative_url(self, location):
        if "://" in location:
            return location
        if location.startswith("//"):
            return f"{self.scheme}:{location}"
        if location.startswith("/"):
            port_suffix = ""
            if (self.scheme == "http" and self.port != 80) or (
                self.scheme == "https" and self.port != 443
            ):
                port_suffix = f":{self.port}"
            return f"{self.scheme}://{self.host}{port_suffix}{location}"

        dir_path = self.path.rsplit("/", 1)[0]
        return f"{self.scheme}://{self.host}:{self.port}{dir_path}/{location}"

    def request(self, redirect_count=0):

        if redirect_count > MAX_REDIRECTS:
            raise Exception("Límite de redirecciones excedido.")

        if self.scheme == "file":
            with open(self.path, "r", encoding="utf8") as f:
                return f.read()

        if self.scheme == "data":
            if "," in self.path:
                media_type, content = self.path.split(",", 1)
                return content
            return ""

        current_url = self.full_url()
        if current_url in CACHE:
            expires_at, cached_content = CACHE[current_url]
            if time.time() < expires_at:
                return cached_content

        while True:
            if (self.host, self.port) in SOCKETS:
                s = SOCKETS[(self.host, self.port)]
            else:
                s = socket.socket(
                    family=socket.AF_INET,
                    type=socket.SOCK_STREAM,
                    proto=socket.IPPROTO_TCP,
                )
                s.connect((self.host, self.port))
                if self.scheme == "https":
                    ctx = ssl.create_default_context()
                    s = ctx.wrap_socket(s, server_hostname=self.host)

                SOCKETS[(self.host, self.port)] = s

            # EJERCICIO 1-9: Anunciar soporte para compresión gzip
            request_headers = {
                "Host": self.host,
                "Connection": "keep-alive",
                "User-Agent": "MiNavegador/1.0",
                "Accept-Encoding": "gzip",
            }

            request = f"GET {self.path} HTTP/1.1\r\n"
            for header, value in request_headers.items():
                request += f"{header}: {value}\r\n"
            request += "\r\n"

            try:
                s.send(request.encode("utf8"))
                response = s.makefile("rb")

                statusline_bytes = response.readline()
                if not statusline_bytes:
                    del SOCKETS[(self.host, self.port)]
                    s.close()
                    continue

                statusline = statusline_bytes.decode("utf-8")
                version, status, explanation = statusline.split(" ", 2)
                break

            except (OSError, ConnectionResetError):
                if (self.host, self.port) in SOCKETS:
                    del SOCKETS[(self.host, self.port)]
                s.close()

        response_headers = {}
        while True:
            line_bytes = response.readline()
            line = line_bytes.decode("utf-8")
            if line == "\r\n" or line == "\n":
                break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        # Redirecciones (3xx)
        if 300 <= int(status) < 400 and "location" in response_headers:
            new_location = response_headers["location"]
            new_url_str = self.resolve_relative_url(new_location)

            if self.view_source:
                new_url_str = "view-source:" + new_url_str

            new_url = URL(new_url_str)
            return new_url.request(redirect_count=redirect_count + 1)

        # EJERCICIO 1-9: Lectura del cuerpo según Transfer-Encoding o Content-Length
        content = b""
        transfer_encoding = response_headers.get("transfer-encoding", "")

        if "chunked" in transfer_encoding.lower():
            # Parsear codificación por fragmentos (chunked)
            while True:
                line = response.readline()
                if not line:
                    break
                # Extraer la longitud hexadecimal (ignorando parámetros tras ';')
                hex_len = line.split(b";")[0].strip()
                if not hex_len:
                    continue
                chunk_len = int(hex_len, 16)
                if chunk_len == 0:
                    # Consumir líneas de tráiler finales
                    while True:
                        trailer = response.readline()
                        if trailer in (b"\r\n", b"\n", b""):
                            break
                    break
                chunk_data = response.read(chunk_len)
                content += chunk_data
                response.readline()  # Consumir la secuencia \r\n que sigue a cada chunk
        elif "content-length" in response_headers:
            n_bytes = int(response_headers["content-length"])
            content = response.read(n_bytes)
        else:
            if (self.host, self.port) in SOCKETS:
                del SOCKETS[(self.host, self.port)]

            s.settimeout(1.0)
            try:
                while True:
                    chunk = response.read(1024)
                    if not chunk:
                        break
                    content += chunk
            except (socket.timeout, TimeoutError):
                pass
            finally:
                s.close()

        # EJERCICIO 1-9: Descomprimir si la respuesta viene codificada en gzip
        content_encoding = response_headers.get("content-encoding", "")
        if "gzip" in content_encoding.lower():
            content = gzip.decompress(content)

        decoded_content = content.decode("utf-8", errors="replace")

        # Caché HTTP
        cache_control = response_headers.get("cache-control", "")
        if "no-store" not in cache_control:
            for directive in cache_control.split(","):
                directive = directive.strip()
                if directive.startswith("max-age="):
                    try:
                        max_age = int(directive.split("=", 1)[1])
                        expires_at = time.time() + max_age
                        CACHE[current_url] = (expires_at, decoded_content)
                    except ValueError:
                        pass

        return decoded_content





if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_url = sys.argv[1]
    else:
        target_url = origen
    browser = Browser()
    browser.load(target_url)
    tkinter.mainloop()