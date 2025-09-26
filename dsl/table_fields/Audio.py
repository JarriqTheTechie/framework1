from framework1.dsl.Table import Field


class Audio(Field):
    def __init__(self, name):
        super().__init__(name)
        self.__type = "audio/mp3"
        self.__src = "insert song url"
        self.__autoplay = ""
        self.__controls = " controls"
        self.__loop = ""
        self.__preload = ""
        self.__muted = ""

    def type(self, type_: str):
        self.__type = type_
        return self

    def src(self, src: str):
        self.__src = src
        return self

    def autoplay(self, autoplay: bool):
        match autoplay:
            case True:
                self.__autoplay = " autoplay"
            case False:
                self.__autoplay = ""
        return self

    def controls(self, controls: bool):
        match controls:
            case True:
                self.__controls = " controls"
            case False:
                self.__controls = ""
        return self

    def loop(self, loop: bool):
        match loop:
            case True:
                self.__loop = " loop"
            case False:
                self.__loop = ""
        return self

    def preload(self, preload: bool):
        match preload:
            case True:
                self.__preload = " preload"
            case False:
                self.__preload = ""
        return self

    def muted(self, muted: bool):
        match muted:
            case True:
                self.__muted = " muted"
            case False:
                self.__muted = ""
        return self

    def _format_value(self, value, record):
        return f"""
            <audio {self.__controls} {self.__autoplay} {self.__muted} {self.__loop} {self.__preload}>
              <source src="{self.__src}" type="{self.__type}" >
              Your browser does not support the audio tag.
            </audio>
        """
