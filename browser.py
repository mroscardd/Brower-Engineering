import socket
import ssl
import sys
import tkinter
import tkinter.font
import re

HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100

FONTS = {}


def get_font(size, weight, style):
    key = (size, weight, style)
    if key not in FONTS:
        font = tkinter.font.Font(size=size, weight=weight, slant=style)
        label = tkinter.Label(font=font)
        FONTS[key] = (font, label)
    return FONTS[key][0]


class Text:

    def __init__(self, text):
        self.text = text


class Tag:

    def __init__(self, tag):
        self.tag = tag


def lex(body):
    out = []
    buffer = ""
    in_tag = False
    for c in body:
        if c == "<":
            in_tag = True
            if buffer:
                out.append(Text(buffer))
            buffer = ""
        elif c == ">":
            in_tag = False
            out.append(Tag(buffer))
            buffer = ""
        else:
            buffer += c
    if not in_tag and buffer:
        out.append(Text(buffer))
    return out


class URL:

    def __init__(self, url):
        self.scheme, url = url.split("://", 1)
        assert self.scheme in ["http", "https"]

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

    def request(self):
        s = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        s.connect((self.host, self.port))

        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)

        request = f"GET {self.path} HTTP/1.0\r\n"
        request += f"Host: {self.host}\r\n"
        request += "\r\n"

        s.send(request.encode("utf8"))
        response = s.makefile("rb")

        statusline = response.readline().decode("utf-8")
        version, status, explanation = statusline.split(" ", 2)

        response_headers = {}
        while True:
            line = response.readline().decode("utf-8")
            if line in ("\r\n", "\n"):
                break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        content = response.read()
        s.close()

        return content.decode("utf-8", errors="replace")


class Layout:

    def __init__(self, tokens, width):
        self.display_list = []
        self.line = []
        self.width = width
        self.cursor_x = HSTEP
        self.cursor_y = VSTEP
        self.weight = "normal"
        self.style = "roman"
        self.size = 12
        self.text_align = "left" 
        self.align_sup = "off" 
        self.abbr = "off"

        for tok in tokens:
            if isinstance(tok, Text):
                self.text(tok.text)
            elif isinstance(tok, Tag):
                self.tag(tok.tag)

        self.flush()

    def text(self, text):
        for word in text.split():
            self.word(word)

    def word(self, word):

        font = get_font(self.size, self.weight, self.style)

        if self.abbr == "on":
            for c in word:
                # Comprobamos el carácter original ANTES de pasarlo a mayúscula
                if c.islower():
                    # Solo las minúsculas originales cambian a mayúscula, tamaño pequeño y negrita
                    char_to_draw = c.upper()
                    char_font = get_font(self.size - 2, "bold", self.style)
                else:
                    # Las mayúsculas originales, números y símbolos mantienen la fuente base
                    char_to_draw = c
                    char_font = font

                cw = char_font.measure(char_to_draw)

                # Comprobación de salto de línea si el carácter no cabe
                if self.cursor_x + cw > self.width - HSTEP:
                    self.flush()

                self.line.append((self.cursor_x, char_to_draw, char_font))
                self.cursor_x += cw

            # Añadimos el espacio correspondiente al final de la palabra
            space_w = font.measure(" ")
            if self.cursor_x + space_w > self.width - HSTEP:
                self.flush()
            else:
                self.cursor_x += space_w
            return
        
        w = font.measure(word)        

        if self.cursor_x + w > self.width - HSTEP:

            self.flush()


        self.line.append((self.cursor_x, word, font))
        self.cursor_x += w + font.measure(" ")

    def tag(self, tag):
        if tag == "b":
            self.weight = "bold"
        elif tag == "/b":
            self.weight = "normal"
        elif tag == "i":
            self.style = "italic"
        elif tag == "/i":
            self.style = "roman"
        elif tag == "small":
            self.size -= 2
        elif tag == "/small":
            self.size += 2
        elif tag == "big":
            self.size += 4
        elif tag == "/big":
            self.size -= 4
        elif tag == "br":
            self.flush()  
        elif tag == "p":
            self.flush()
        elif tag == "/p":
            self.flush()
            self.cursor_y += VSTEP  
        elif tag == 'h1 class="title"':
            self.flush()    
            self.text_align = "center" 
            self.size = 18
        elif tag == "/h1":
            self.flush()
            self.text_align = "left" 
            self.size = 12
            self.cursor_y += VSTEP   
        elif tag == "sup":
            self.align_sup = "on"
            self.size = self.size //  2
        elif tag == "/sup":
            self.size = self.size * 2     
            self.align_sup = "off" 
        elif tag == "abbr":
            self.abbr = "on"
        elif tag == "/abbr":
            self.abbr = "off"    
            


    def flush(self):
        if not self.line:
            return

        metrics = [font.metrics() for x, word, font in self.line]
        max_ascent = max([metric["ascent"] for metric in metrics])
        max_descent = max([metric["descent"] for metric in metrics])

        baseline = self.cursor_y + 1.25 * max_ascent

        if self.text_align == "center":
            last_x, last_word, last_font = self.line[-1]
            line_width = (last_x + last_font.measure(last_word)) - HSTEP
            margin = (self.width - 2 * HSTEP) - line_width

            offset = max(0, margin / 2)
        else: 
            offset = 0 

           
        for x, word, font in self.line:
            y = baseline - font.metrics("ascent")
            if self.align_sup == "on":
                y -= font.metrics("ascent") * 0.4

            self.display_list.append((x + offset, y, word, font))
                
        self.cursor_x = HSTEP
        self.line = []
        self.cursor_y += 1.25 * (max_ascent + max_descent)


class Browser:

    def __init__(self):
        self.width = 800
        self.height = 600
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window,
            width=self.width,
            height=self.height,
        )
        self.canvas.pack(fill="both", expand=True)

        self.display_list = []
        self.scroll = 0
        self.nodes = []

        self.window.bind("<Down>", self.scrolldown)
        self.window.bind("<Up>", self.scrollup)
        self.window.bind("<MouseWheel>", self.on_mousewheel)
        self.window.bind("<Configure>", self.on_resize)

    def load(self, url):
        body = URL(url).request()
        self.nodes = lex(body)
        self.display_list = Layout(self.nodes, self.width).display_list
        self.draw()

    def draw(self):
        self.canvas.delete("all")

        for x, y, word, font in self.display_list:
            if y > self.scroll + self.height:
                continue
            if y + font.metrics("linespace") < self.scroll:
                continue

            self.canvas.create_text(
                x,
                y - self.scroll,
                text=word,
                font=font,
                anchor="nw",
            )

    def scrolldown(self, e):
        if self.display_list:
            max_y = max(y for x, y, word, font in self.display_list)
            if self.scroll < max_y - self.height:
                self.scroll += SCROLL_STEP
                self.draw()

    def scrollup(self, e):
        if self.scroll >= SCROLL_STEP:
            self.scroll -= SCROLL_STEP
            self.draw()

    def on_mousewheel(self, e):
        if e.delta > 0:
            self.scrollup(e)
        else:
            self.scrolldown(e)

    def on_resize(self, e):
        if e.width == self.width and e.height == self.height:
            return
        self.width = e.width
        self.height = e.height
        if self.nodes:
            self.display_list = Layout(self.nodes, self.width).display_list
            self.draw()


if __name__ == "__main__":
    browser = Browser()
    browser.load(sys.argv[1])
    tkinter.mainloop()