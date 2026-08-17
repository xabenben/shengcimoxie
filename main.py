import time
import threading
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.slider import Slider
from kivy.uix.popup import Popup

# 尝试导入 Android 原生 TTS 接口
try:
    from jnius import autoclass
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
    Locale = autoclass('java.util.Locale')
    HAS_ANDROID_TTS = True
except Exception:
    HAS_ANDROID_TTS = False

class AndroidTTS:
    """Android 原生 TTS 语音引擎封装"""
    def __init__(self):
        self.tts = None
        self.is_ready = False
        if HAS_ANDROID_TTS:
            activity = PythonActivity.mActivity
            
            class TTSListener(autoclass('android.speech.tts.TextToSpeech$OnInitListener')):
                def __init__(self, outer):
                    super().__init__()
                    self.outer = outer
                def onInit(self, status):
                    if status == TextToSpeech.SUCCESS:
                        self.outer.tts.setLanguage(Locale.CHINESE)
                        self.outer.is_ready = True

            self.listener = TTSListener(self)
            self.tts = TextToSpeech(activity, self.listener)

    def speak(self, text, rate_val):
        if not HAS_ANDROID_TTS or not self.tts or not self.is_ready:
            time.sleep(1) # 桌面测试模拟发声耗时
            return
        
        # 将 120-240 范围映射到 Android TTS 语速倍率 (0.75x ~ 1.5x)
        speech_rate = rate_val / 160.0
        self.tts.setSpeechRate(speech_rate)
        
        # 调用原生 speak
        self.tts.speak(text, TextToSpeech.QUEUE_FLUSH, None, "WordReaderID")
        
        # 阻塞当前线程直到朗读完毕
        while self.tts.isSpeaking():
            time.sleep(0.05)

class WordReaderApp(App):
    def build(self):
        self.title = "汉字词汇朗读器"
        
        # 运行与控制标志
        self.is_running = False
        self.is_paused = False
        self.restart_all = False
        self.target_index = -1
        
        self.tts_engine = AndroidTTS()

        root = BoxLayout(orientation='vertical', padding=10, spacing=8)

        # 1. 设置区 (网格布局)
        settings_grid = GridLayout(cols=2, spacing=5, size_hint_y=None, height=160)
        
        settings_grid.add_widget(Label(text="每词念几遍:"))
        self.repeat_times_input = TextInput(text="3", input_filter="int", multiline=False)
        settings_grid.add_widget(self.repeat_times_input)

        settings_grid.add_widget(Label(text="重复间隔(秒):"))
        self.repeat_interval_input = TextInput(text="1", input_filter="int", multiline=False)
        settings_grid.add_widget(self.repeat_interval_input)

        settings_grid.add_widget(Label(text="词汇间隔(秒):"))
        self.word_interval_input = TextInput(text="5", input_filter="int", multiline=False)
        settings_grid.add_widget(self.word_interval_input)

        settings_grid.add_widget(Label(text="语速(120-240):"))
        self.rate_input = TextInput(text="160", input_filter="int", multiline=False)
        settings_grid.add_widget(self.rate_input)

        root.add_widget(settings_grid)

        # 2. 文本输入区
        root.add_widget(Label(text="请输入汉字词汇（按空格或换行分隔）:", size_hint_y=None, height=30))
        self.text_input = TextInput(
            text="苹果 香蕉 葡萄 橘子 猕猴桃 鸭梨 吐司",
            multiline=True,
            font_name="Roboto"
        )
        root.add_widget(self.text_input)

        # 3. 进度条区域
        progress_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, spacing=5)
        progress_box.add_widget(Label(text="进度:", size_hint_x=None, width=50))
        
        self.slider = Slider(min=0, max=100, value=0)
        self.slider.bind(value=self.on_slider_change)
        progress_box.add_widget(self.slider)

        self.progress_label = Label(text="0%", size_hint_x=None, width=60)
        progress_box.add_widget(self.progress_label)
        root.add_widget(progress_box)

        # 4. 按钮区
        btn_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=5)
        
        self.btn_start = Button(text="开始", on_press=self.start_reading)
        self.btn_pause = Button(text="暂停", disabled=True, on_press=self.toggle_pause)
        self.btn_restart = Button(text="重读", disabled=True, on_press=self.restart_reading)
        self.btn_stop = Button(text="停止", disabled=True, on_press=self.stop_reading)

        btn_box.add_widget(self.btn_start)
        btn_box.add_widget(self.btn_pause)
        btn_box.add_widget(self.btn_restart)
        btn_box.add_widget(self.btn_stop)
        root.add_widget(btn_box)

        # 5. 状态栏
        self.status_label = Label(text="就绪", size_hint_y=None, height=30, color=(0.7, 0.7, 0.7, 1))
        root.add_widget(self.status_label)

        return root

    def update_status(self, text):
        Clock.schedule_once(lambda dt: setattr(self.status_label, 'text', text))

    def update_progress_ui(self, pct):
        def _update(dt):
            self.slider.value = pct
            self.progress_label.text = f"{int(pct)}%"
        Clock.schedule_once(_update)

    def set_inputs_disabled(self, disabled):
        def _set(dt):
            self.repeat_times_input.disabled = disabled
            self.repeat_interval_input.disabled = disabled
            self.word_interval_input.disabled = disabled
            self.rate_input.disabled = disabled
        Clock.schedule_once(_set)

    def on_slider_change(self, instance, value):
        if self.is_running:
            words = [w for w in self.text_input.text.split() if w.strip()]
            if words:
                target = int((value / 100.0) * len(words))
                if target >= len(words):
                    target = len(words) - 1
                self.target_index = target

    def toggle_pause(self, instance):
        if not self.is_running:
            return
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.btn_pause.text = "继续"
            self.set_inputs_disabled(False) # 暂停时允许修改设置
            self.update_status("已暂停朗读 (可修改参数)...")
        else:
            self.btn_pause.text = "暂停"
            self.set_inputs_disabled(True)

    def restart_reading(self, instance):
        if not self.is_running:
            return
        self.restart_all = True
        if self.is_paused:
            self.toggle_pause(None)

    def stop_reading(self, instance):
        self.is_running = False
        self.is_paused = False
        self.restart_all = False
        self.target_index = -1
        self.reset_ui()
        self.update_status("已停止，恢复初始状态")

    def countdown_sleep(self, get_sec_func, prefix):
        elapsed = 0
        while True:
            try:
                target_sec = int(get_sec_func())
            except ValueError:
                target_sec = 0

            if elapsed >= target_sec:
                return True

            if not self.is_running or self.restart_all or self.target_index != -1:
                return False

            while self.is_paused:
                if not self.is_running or self.restart_all or self.target_index != -1:
                    return False
                time.sleep(0.1)

            rem = target_sec - elapsed
            self.update_status(f"{prefix} 倒计时 {rem} 秒...")
            time.sleep(1)
            elapsed += 1

    def read_words_process(self):
        while True:
            self.restart_all = False
            words = [w for w in self.text_input.text.split() if w.strip()]
            if not words:
                self.update_status("提示: 请输入词汇！")
                self.reset_ui()
                return

            total = len(words)
            idx = 0
            cancelled = False

            while idx < total:
                if self.target_index != -1:
                    idx = self.target_index
                    self.target_index = -1

                if not self.is_running or self.restart_all:
                    cancelled = self.restart_all
                    break

                word = words[idx]
                pct = ((idx + 1) / total) * 100.0
                self.update_progress_ui(pct)

                read_ok = True
                times = 1

                while True:
                    try:
                        max_times = int(self.repeat_times_input.text)
                    except ValueError:
                        max_times = 1

                    if times > max_times:
                        break

                    while self.is_paused:
                        if not self.is_running or self.restart_all or self.target_index != -1:
                            break
                        time.sleep(0.1)

                    if not self.is_running or self.restart_all or self.target_index != -1:
                        read_ok = False
                        cancelled = self.restart_all
                        break

                    try:
                        rate_val = int(self.rate_input.text)
                    except ValueError:
                        rate_val = 160

                    self.update_status(f"朗读({idx+1}/{total}): 【{word}】 第{times}/{max_times}遍")
                    self.tts_engine.speak(word, rate_val)

                    if times < max_times:
                        if not self.countdown_sleep(lambda: self.repeat_interval_input.text, f"【{word}】间隔"):
                            read_ok = False
                            cancelled = self.restart_all
                            break

                    times += 1

                if not read_ok:
                    if self.target_index != -1:
                        continue
                    break

                if idx < total - 1:
                    if not self.countdown_sleep(lambda: self.word_interval_input.text, f"【{word}】完成"):
                        cancelled = self.restart_all
                        if self.target_index != -1:
                            continue
                        break

                idx += 1

            if cancelled and self.is_running:
                continue
            else:
                break

        if self.is_running and not self.restart_all and self.target_index == -1:
            self.update_progress_ui(100)
            self.update_status("全部词汇朗读完成！")

        self.reset_ui()

    def start_reading(self, instance):
        if self.is_running:
            return
        self.is_running = True
        self.is_paused = False
        self.restart_all = False
        self.target_index = -1

        self.set_inputs_disabled(True)
        self.btn_start.disabled = True
        self.btn_pause.disabled = False
        self.btn_restart.disabled = False
        self.btn_stop.disabled = False

        threading.Thread(target=self.read_words_process, daemon=True).start()

    def reset_ui(self):
        def _reset(dt):
            self.is_running = False
            self.is_paused = False
            self.restart_all = False
            self.target_index = -1
            self.btn_start.disabled = False
            self.btn_pause.disabled = True
            self.btn_pause.text = "暂停"
            self.btn_restart.disabled = True
            self.btn_stop.disabled = True
            self.set_inputs_disabled(False)
        Clock.schedule_once(_reset)

if __name__ == "__main__":
    WordReaderApp().run()