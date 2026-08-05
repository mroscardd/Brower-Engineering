import socket
import ssl
import sys

origen = "file://local/index.html"

class URL:
    def __init__(self, url=origen):

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

    def request (self):

        if self.scheme == "file":
            with open(self.path, "r", encoding="utf8") as f:
                return f.read()

        if self.scheme == "data":
            if "," in self.path:
                media_type, content = self.path.split(",", 1)
                return content
            return ""
             
        # Creamos conexion Socket
        s = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto = socket.IPPROTO_TCP,
        )
        s.connect((self.host, self.port))
        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)

        request_headers = {
        "Host": self.host,
        "Connection": "close",
        "User-Agent": "MiNavegador/1.0"
        }    

        # Creamos la request
        request = f"GET {self.path} HTTP/1.1\r\n"

        for header, value in request_headers.items():
            request += f"{header}: {value}\r\n"

        request += "\r\n"

        s.send(request.encode("utf8"))

        # Leemos la version
        response = s.makefile("r", encoding="utf8", newline="\r\n")
        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)

        # Obtenemos los headers
        response_headers = {}
        while True:
            line = response.readline()
            if line == "\r\n": break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        #assert "transfer-encoding" not in response_headers
        #assert "content-encoding" not in response_headers

        #Obtenemos el cuerpo
        content = response.read()
        s.close()
        return content

    def show(self, body):
        # Filtra el html
        content = ""
        in_tag = False
        for c in body:
            if c == "<":
                in_tag = True
            elif c == ">":
                in_tag = False
            elif not in_tag:
                content += c
    
        content = content.replace("&lt;", "<")
        content = content.replace("&gt;", ">")        
        print(content)    

    def load(self):
        body = self.request()
        if self.view_source == True:
            print(body)
            return
        self.show(body)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_url = sys.argv[1]
    else:
        target_url = origen
    link = URL((target_url))
    link.load()
