import socket
import ssl
import sys
import tkinter
import tkinter.font

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

    def flush(self):
        if not self.line:
            return

        metrics = [font.metrics() for x, word, font in self.line]
        max_ascent = max([metric["ascent"] for metric in metrics])
        max_descent = max([metric["descent"] for metric in metrics])

        baseline = self.cursor_y + 1.25 * max_ascent

        for x, word, font in self.line:
            y = baseline - font.metrics("ascent")
            self.display_list.append((x, y, word, font))

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