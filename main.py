"""
漫画リーダー GUI アプリケーション（本格運用版）
フォルダ構造から自動的に章を検出し、ページ画像を表示します。
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
from pathlib import Path
from PIL import Image, ImageTk
import json
import re
import logging
import sys
from datetime import datetime
import traceback

# ============ ロギング設定 ============
def setup_logger():
    """ロギング機能の初期化"""
    log_dir = os.path.join(os.path.expanduser("~"), ".comic_reader_logs")
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, f"comic_reader_{datetime.now().strftime('%Y%m%d')}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logger()

# ============ 高 DPI 対応 ============
def enable_windows_dpi_awareness():
    """Windows の高 DPI 表示を有効化して GUI をシャープにする"""
    if sys.platform != "win32":
        return

    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        logger.info("Windows DPI awareness enabled: PROCESS_PER_MONITOR_DPI_AWARE")
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
            logger.info("Windows DPI awareness enabled: SetProcessDPIAware")
        except Exception:
            logger.warning("Windows DPI awareness could not be enabled")

# ============ テーマカラー ============
THEME = {
    'bg_main': '#1e1e1e',
    'bg_panel': '#2d2d2d',
    'bg_sidebar': '#252525',
    'fg_text': '#e0e0e0',
    'fg_accent': '#64b5f6',
    'button_bg': '#3a3a3a',
    'button_hover': '#4a4a4a',
    'accent': '#64b5f6',
}

def natural_sort_key(text):
    """自然順ソートのキー関数"""
    return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', text)]

class ComicReader:
    def __init__(self, root):
        self.root = root
        self.root.title("漫画リーダー - v1.0")
        self.touch_mode = False
        self.touch_buttons = []
        self.touch_widgets = []
        self._configure_scaling()
        self.apply_custom_style()
        
        # データ構造
        self.root_path = None
        self.chapters = []
        self.current_chapter_idx = 0
        self.current_page_idx = 0
        self.images = []
        self.photo_image = None
        self.image_cache = {}
        self.MAX_CACHE_SIZE = 10
        
        # 設定ファイルパス
        self.config_dir = os.path.join(os.path.expanduser("~"), ".comic_reader")
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_file = os.path.join(self.config_dir, "config.json")
        
        logger.info("="*50)
        logger.info("漫画リーダー起動")
        logger.info(f"設定ディレクトリ: {self.config_dir}")
        
        self.setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        try:
            self.load_last_position()
            logger.info("前回の位置を復元しました")
        except Exception as e:
            logger.warning(f"前回の位置の復元に失敗: {e}")
        
        # キーバインド
        self.root.bind("<Right>", self.on_key_next)
        self.root.bind("<Left>", self.on_key_prev)
        self.root.bind("<space>", self.on_key_next)
        self.root.bind("<BackSpace>", self.on_key_prev)
        self.root.bind("<Up>", self.on_key_chapter_prev)
        self.root.bind("<Down>", self.on_key_chapter_next)
        self.root.bind("<MouseWheel>", self.on_mousewheel)
        self.root.bind("<Home>", lambda e: self.first_chapter())
        self.root.bind("<End>", lambda e: self.last_chapter())
        self.root.bind("<Control-o>", lambda e: self.select_folder())
        self.root.bind("<F11>", lambda e: self.toggle_fullscreen())
        self.root.bind("<Escape>", lambda e: self.exit_fullscreen())
        
        logger.info("UI初期化完了")
        
    def setup_ui(self):
        """UIの初期化"""
        self.root.config(bg=THEME['bg_main'])
        
        # トップバー
        top_bar = tk.Frame(self.root, bg=THEME['bg_panel'], height=58)
        top_bar.pack(side=tk.TOP, fill=tk.X)
        top_bar.pack_propagate(False)
        
        ttk.Button(top_bar, text="📁 フォルダを開く", command=self.select_folder).pack(side=tk.LEFT, padx=10, pady=10)
        
        self.touch_mode_button = ttk.Button(top_bar, text="タッチモード: OFF", command=self.toggle_touch_mode)
        self.touch_mode_button.pack(side=tk.RIGHT, padx=10, pady=10)
        self.touch_buttons.append(self.touch_mode_button)
        
        self.title_label = tk.Label(top_bar, text="漫画リーダー", bg=THEME['bg_panel'], 
                                    fg=THEME['fg_text'], font=("Arial", 14, "bold"))
        self.title_label.pack(side=tk.LEFT, padx=10, pady=10)
        
        self.folder_label = tk.Label(top_bar, text="フォルダが選択されていません", bg=THEME['bg_panel'], 
                                     fg=THEME['fg_accent'], font=("Arial", 10))
        self.folder_label.pack(side=tk.LEFT, padx=10, pady=10, fill=tk.X, expand=True)
        
        # メインコンテンツ
        content_frame = tk.Frame(self.root, bg=THEME['bg_main'])
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # サイドバー
        sidebar = tk.Frame(content_frame, bg=THEME['bg_sidebar'], width=220)
        sidebar.pack(side=tk.LEFT, fill=tk.BOTH, padx=0)
        sidebar.pack_propagate(False)
        
        sidebar_title = tk.Label(sidebar, text="📚 章一覧", bg=THEME['bg_sidebar'], 
                                fg=THEME['fg_text'], font=("Arial", 10, "bold"))
        sidebar_title.pack(padx=10, pady=10, fill=tk.X)
        
        list_frame = tk.Frame(sidebar, bg=THEME['bg_sidebar'])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.chapter_listbox = tk.Listbox(list_frame, bg=THEME['bg_panel'], 
                                          fg=THEME['fg_text'], selectmode=tk.SINGLE,
                                          yscrollcommand=scrollbar.set, font=("Arial", 9),
                                          activestyle='none', highlightthickness=0, relief=tk.FLAT)
        self.chapter_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.chapter_listbox.bind('<<ListboxSelect>>', self.on_chapter_listbox_select)
        scrollbar.config(command=self.chapter_listbox.yview)
        
        # 画像表示エリア
        center_frame = tk.Frame(content_frame, bg=THEME['bg_main'])
        center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.image_label = tk.Label(center_frame, bg=THEME['bg_panel'], relief=tk.FLAT)
        self.image_label.pack(fill=tk.BOTH, expand=True)
        
        # ボトムバー
        bottom_bar = tk.Frame(self.root, bg=THEME['bg_panel'])
        bottom_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        info_frame = tk.Frame(bottom_bar, bg=THEME['bg_panel'])
        info_frame.pack(fill=tk.X, padx=10, pady=10)
    
        
        self.page_info = tk.Label(info_frame, text="ページ情報", bg=THEME['bg_panel'], 
                                 fg=THEME['fg_text'], font=("Arial", 10))
        self.page_info.pack(side=tk.LEFT)
        
        self.progress_bar = ttk.Progressbar(info_frame, mode='determinate', length=300)
        self.progress_bar.pack(side=tk.LEFT, padx=20, fill=tk.X, expand=True)
        
        control_frame = tk.Frame(bottom_bar, bg=THEME['bg_panel'])
        control_frame.pack(fill=tk.X, padx=10, pady=(0, 18))
        
        left_group = tk.Frame(control_frame, bg=THEME['bg_panel'])
        left_group.pack(side=tk.LEFT)
        
        self.prev_chapter_button = ttk.Button(left_group, text="⏮ 最初の話", command=self.first_chapter)
        self.prev_chapter_button.pack(side=tk.LEFT, padx=6, pady=6)
        self.touch_buttons.append(self.prev_chapter_button)
        
        self.prev_chapter_button2 = ttk.Button(left_group, text="⬅ 前の話", command=self.prev_chapter_btn)
        self.prev_chapter_button2.pack(side=tk.LEFT, padx=6, pady=6)
        self.touch_buttons.append(self.prev_chapter_button2)
        
        self.prev_page_button = ttk.Button(left_group, text="⬅ 前ページ", command=self.prev_page)
        self.prev_page_button.pack(side=tk.LEFT, padx=6, pady=6)
        self.touch_buttons.append(self.prev_page_button)
        
        center_group = tk.Frame(control_frame, bg=THEME['bg_panel'])
        center_group.pack(side=tk.LEFT, expand=True, padx=20)
        
        self.page_label = tk.Label(center_group, text="ページ:", bg=THEME['bg_panel'], fg=THEME['fg_text'], font=("Arial", 10))
        self.page_label.pack(side=tk.LEFT, padx=6, pady=6)
        self.touch_widgets.append(self.page_label)
        
        self.page_input = tk.Entry(center_group, width=8, bg=THEME['button_bg'], 
                                  fg=THEME['fg_text'], font=("Arial", 11), relief=tk.FLAT)
        self.page_input.pack(side=tk.LEFT, padx=6, pady=6)
        self.touch_widgets.append(self.page_input)
        self.page_input.bind("<Return>", self.on_page_input)
        
        self.jump_button = ttk.Button(center_group, text="移動", command=self.jump_to_page)
        self.jump_button.pack(side=tk.LEFT, padx=6, pady=6)
        self.touch_buttons.append(self.jump_button)
        
        right_group = tk.Frame(control_frame, bg=THEME['bg_panel'])
        right_group.pack(side=tk.RIGHT)
        
        self.next_page_button = ttk.Button(right_group, text="次ページ ➡", command=self.next_page)
        self.next_page_button.pack(side=tk.LEFT, padx=6, pady=6)
        self.touch_buttons.append(self.next_page_button)
        
        self.next_chapter_button = ttk.Button(right_group, text="次の話 ➡", command=self.next_chapter_btn)
        self.next_chapter_button.pack(side=tk.LEFT, padx=6, pady=6)
        self.touch_buttons.append(self.next_chapter_button)
        
        self.last_chapter_button = ttk.Button(right_group, text="最後の話 ⏭", command=self.last_chapter)
        self.last_chapter_button.pack(side=tk.LEFT, padx=6, pady=6)
        self.touch_buttons.append(self.last_chapter_button)
        
        # ヒント
        hint_frame = tk.Frame(self.root, bg=THEME['bg_main'])
        hint_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=2)
        hint_label = tk.Label(hint_frame, text="⌨️ [→/Space] 次ページ | [←/BackSpace] 前ページ | [↑] 前の話 | [↓] 次の話 | [Home] 最初 | [End] 最後 | 🖱 ホイール移動", 
                             bg=THEME['bg_main'], fg="#666666", font=("Arial", 8))
        hint_label.pack(side=tk.LEFT)
    
    def toggle_fullscreen(self):
        """フルスクリーン切り替え"""
        if self.root.attributes('-fullscreen'):
            self.root.attributes('-fullscreen', False)
        else:
            self.root.attributes('-fullscreen', True)
        logger.info(f"フルスクリーン: {'ON' if self.root.attributes('-fullscreen') else 'OFF'}")
    
    def exit_fullscreen(self):
        """フルスクリーン終了"""
        self.root.attributes('-fullscreen', False)
    
    def select_folder(self):
        """フォルダ選択"""
        try:
            folder = filedialog.askdirectory(title="漫画フォルダを選択")
            if folder:
                logger.info(f"フォルダ選択: {folder}")
                self.root_path = folder
                self.clear_image_cache()
                self.load_chapters()
        except Exception as e:
            logger.error(f"フォルダ選択エラー: {e}")
            messagebox.showerror("エラー", f"フォルダ選択エラー: {str(e)}")
    
    def load_chapters(self):
        """章を読み込む"""
        self.chapters = []
        
        try:
            entries = sorted(os.listdir(self.root_path), key=natural_sort_key)
            for entry in entries:
                full_path = os.path.join(self.root_path, entry)
                if os.path.isdir(full_path):
                    self.chapters.append((entry, full_path))
            
            if not self.chapters:
                logger.warning("フォルダが見つかりません")
                messagebox.showwarning("警告", "フォルダが見つかりません")
                return
            
            logger.info(f"読み込み完了: {len(self.chapters)}個の章")
            
            self.folder_label.config(text=self.root_path)
            self.title_label.config(text=f"漫画リーダー - {os.path.basename(self.root_path)}")
            
            self.chapter_listbox.delete(0, tk.END)
            for chapter_name, _ in self.chapters:
                self.chapter_listbox.insert(tk.END, chapter_name)
            
            self.current_chapter_idx = 0
            self.chapter_listbox.selection_set(0)
            self.chapter_listbox.see(0)
            self.load_chapter(0)
            
        except Exception as e:
            logger.error(f"フォルダ読み込みエラー: {e}")
            messagebox.showerror("エラー", f"フォルダ読み込みエラー: {str(e)}")
    
    def load_chapter(self, chapter_idx):
        """章のページを読み込む"""
        if chapter_idx < 0 or chapter_idx >= len(self.chapters):
            logger.warning(f"無効な章インデックス: {chapter_idx}")
            return
        
        try:
            self.current_chapter_idx = chapter_idx
            chapter_name, chapter_path = self.chapters[chapter_idx]
            
            self.images = []
            files = sorted(os.listdir(chapter_path), key=natural_sort_key)
            
            for file in files:
                full_path = os.path.join(chapter_path, file)
                if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                    self.images.append(full_path)
            
            if not self.images:
                logger.warning(f"{chapter_name}: 画像ファイルが見つかりません")
                messagebox.showwarning("警告", f"{chapter_name}: 画像ファイルが見つかりません")
                return
            
            logger.info(f"章読み込み: {chapter_name} ({len(self.images)}ページ)")
            
            self.current_page_idx = 0
            self.display_page()
            
        except Exception as e:
            logger.error(f"チャプター読み込みエラー: {e}")
            messagebox.showerror("エラー", f"チャプター読み込みエラー: {str(e)}")
    
    def on_chapter_listbox_select(self, event):
        """リストボックス選択"""
        selection = self.chapter_listbox.curselection()
        if selection:
            self.load_chapter(selection[0])
    
    def display_page(self):
        """ページを表示（高品質リサイズ対応）"""
        if not self.images or self.current_page_idx < 0 or self.current_page_idx >= len(self.images):
            return
        
        try:
            image_path = self.images[self.current_page_idx]
            chapter_name = self.chapters[self.current_chapter_idx][0]
            page_num = self.current_page_idx + 1
            total_pages = len(self.images)
            
            # キャッシュから取得またはロード
            if image_path not in self.image_cache:
                image = Image.open(image_path)
                
                # 色空間をRGBに統一（品質向上）
                if image.mode != 'RGB':
                    if image.mode == 'RGBA':
                        # 透過情報を失わないように背景を白で埋める
                        bg = Image.new('RGB', image.size, (255, 255, 255))
                        bg.paste(image, mask=image.split()[3])
                        image = bg
                    else:
                        image = image.convert('RGB')
                
                # 高品質リサイズ
                image = self._high_quality_resize(image, (1050, 620))
                
                self.image_cache[image_path] = image
                
                if len(self.image_cache) > self.MAX_CACHE_SIZE:
                    oldest_key = next(iter(self.image_cache))
                    del self.image_cache[oldest_key]
                    logger.debug(f"キャッシュ削除: {oldest_key}")
                
                logger.debug(f"画像ロード: {os.path.basename(image_path)}")
            else:
                image = self.image_cache[image_path]
            
            self.photo_image = ImageTk.PhotoImage(image)
            self.image_label.config(image=self.photo_image)
            
            self.page_info.config(text=f"📖 {chapter_name} - ページ {page_num}/{total_pages}")
            
            progress = (page_num / total_pages) * 100
            self.progress_bar['value'] = progress
            
            self.page_input.delete(0, tk.END)
            self.page_input.insert(0, str(page_num))
            
            self.save_last_position()
            
        except Exception as e:
            logger.error(f"ページ表示エラー: {e}")
            messagebox.showerror("エラー", f"画像表示エラー: {str(e)}")
    
    def _high_quality_resize(self, image, max_size):
        """高品質なリサイズ処理"""
        # 元画像サイズ
        orig_width, orig_height = image.size
        max_width, max_height = max_size
        
        # アスペクト比を保持したサイズを計算
        ratio = min(max_width / orig_width, max_height / orig_height)
        
        # 縮小率が大きい場合は段階的にリサイズ（品質向上）
        if ratio < 0.5:
            # 50%以下の縮小は段階的に行う
            temp_size = (int(orig_width * 0.5), int(orig_height * 0.5))
            image = image.resize(temp_size, Image.Resampling.LANCZOS)
            logger.debug(f"段階的リサイズ第1段階: {orig_width}x{orig_height} → {temp_size}")
        
        # 最終サイズにリサイズ
        new_size = (int(orig_width * ratio), int(orig_height * ratio))
        image = image.resize(new_size, Image.Resampling.LANCZOS)
        logger.debug(f"最終リサイズ: {new_size}")
        
        return image
    
    def next_page(self):
        """次ページ"""
        if not self.images:
            return
        
        self.current_page_idx += 1
        
        if self.current_page_idx >= len(self.images):
            self.current_page_idx = 0
            next_chapter_idx = self.current_chapter_idx + 1
            
            if next_chapter_idx < len(self.chapters):
                logger.info(f"次の章へ移動: {next_chapter_idx}")
                self.chapter_listbox.selection_clear(0, tk.END)
                self.chapter_listbox.selection_set(next_chapter_idx)
                self.chapter_listbox.see(next_chapter_idx)
                self.load_chapter(next_chapter_idx)
            else:
                logger.info("すべての漫画を読み終わりました")
                messagebox.showinfo("完了", "🎉 すべての漫画を読み終わりました！")
                self.current_page_idx = len(self.images) - 1
                self.display_page()
        else:
            self.display_page()
    
    def prev_page(self):
        """前ページ"""
        if not self.images:
            return
        
        self.current_page_idx -= 1
        
        if self.current_page_idx < 0:
            prev_chapter_idx = self.current_chapter_idx - 1
            
            if prev_chapter_idx >= 0:
                logger.info(f"前の章へ移動: {prev_chapter_idx}")
                self.chapter_listbox.selection_clear(0, tk.END)
                self.chapter_listbox.selection_set(prev_chapter_idx)
                self.chapter_listbox.see(prev_chapter_idx)
                self.load_chapter(prev_chapter_idx)
                self.current_page_idx = len(self.images) - 1
                self.display_page()
            else:
                self.current_page_idx = 0
                self.display_page()
        else:
            self.display_page()
    
    def jump_to_page(self):
        """ページジャンプ"""
        try:
            page_num = int(self.page_input.get())
            if 1 <= page_num <= len(self.images):
                self.current_page_idx = page_num - 1
                self.display_page()
            else:
                messagebox.showwarning("警告", f"ページ番号は 1 から {len(self.images)} の間で入力してください")
        except ValueError:
            messagebox.showwarning("警告", "有効なページ番号を入力してください")
    
    def on_page_input(self, event):
        """ページ入力Enterキー"""
        self.jump_to_page()
    
    def on_key_next(self, event):
        """次ページキー"""
        self.next_page()
    
    def on_key_prev(self, event):
        """前ページキー"""
        self.prev_page()
    
    def on_key_chapter_next(self, event):
        """次章キー"""
        self.next_chapter_btn()
    
    def on_key_chapter_prev(self, event):
        """前章キー"""
        self.prev_chapter_btn()
    
    def on_mousewheel(self, event):
        """マウスホイール"""
        if event.delta > 0:
            self.prev_page()
        else:
            self.next_page()
    
    def first_chapter(self):
        """最初の章"""
        if self.chapters:
            self.chapter_listbox.selection_clear(0, tk.END)
            self.chapter_listbox.selection_set(0)
            self.chapter_listbox.see(0)
            self.load_chapter(0)
    
    def last_chapter(self):
        """最後の章"""
        if self.chapters:
            last_idx = len(self.chapters) - 1
            self.chapter_listbox.selection_clear(0, tk.END)
            self.chapter_listbox.selection_set(last_idx)
            self.chapter_listbox.see(last_idx)
            self.load_chapter(last_idx)
    
    def prev_chapter_btn(self):
        """前の章"""
        if self.current_chapter_idx > 0:
            self.chapter_listbox.selection_clear(0, tk.END)
            self.chapter_listbox.selection_set(self.current_chapter_idx - 1)
            self.chapter_listbox.see(self.current_chapter_idx - 1)
            self.load_chapter(self.current_chapter_idx - 1)
    
    def next_chapter_btn(self):
        """次の章"""
        if self.current_chapter_idx < len(self.chapters) - 1:
            self.chapter_listbox.selection_clear(0, tk.END)
            self.chapter_listbox.selection_set(self.current_chapter_idx + 1)
            self.chapter_listbox.see(self.current_chapter_idx + 1)
            self.load_chapter(self.current_chapter_idx + 1)
    
    def save_last_position(self):
        """位置を保存"""
        if not self.root_path:
            return
        
        try:
            geometry = self.root.geometry()
            is_fullscreen = self.root.attributes('-fullscreen')
            
            config = {
                "root_path": self.root_path,
                "chapter_idx": self.current_chapter_idx,
                "page_idx": self.current_page_idx,
                "geometry": geometry,
                "fullscreen": is_fullscreen,
                "last_saved": datetime.now().isoformat()
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"位置保存: {config['chapter_idx']}-{config['page_idx']}")
        except Exception as e:
            logger.error(f"位置保存エラー: {e}")
    
    def load_last_position(self):
        """位置を復元"""
        if not os.path.exists(self.config_file):
            self.root.geometry("1100x750")
            return
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            if "geometry" in config:
                try:
                    self.root.geometry(config["geometry"])
                except:
                    self.root.geometry("1100x750")
            
            if config.get("fullscreen", False):
                self.root.attributes('-fullscreen', True)
            
            last_root = config.get("root_path")
            if last_root and os.path.exists(last_root):
                self.root_path = last_root
                logger.info(f"フォルダ復元: {last_root}")
                
                try:
                    self.load_chapters()
                    self.current_chapter_idx = min(config.get("chapter_idx", 0), len(self.chapters) - 1)
                    self.load_chapter(self.current_chapter_idx)
                    self.current_page_idx = min(config.get("page_idx", 0), len(self.images) - 1)
                    self.display_page()
                    logger.info(f"位置復元: 第{self.current_chapter_idx}章 - ページ{self.current_page_idx + 1}")
                except Exception as e:
                    logger.error(f"フォルダ復元エラー: {e}")
            else:
                self.root.geometry("1100x750")
        except Exception as e:
            logger.error(f"設定読み込みエラー: {e}")
            self.root.geometry("1100x750")
    
    def clear_image_cache(self):
        """キャッシュクリア"""
        try:
            for img in self.image_cache.values():
                del img
            self.image_cache.clear()
            if self.photo_image:
                del self.photo_image
            logger.debug("画像キャッシュをクリアしました")
        except Exception as e:
            logger.warning(f"キャッシュクリアエラー: {e}")

    def _configure_scaling(self):
        """画面 DPI に応じて Tkinter のスケーリングを調整する"""
        try:
            dpi = self.root.winfo_fpixels('1i')
            scale = max(1.0, dpi / 72.0)
            self.root.tk.call('tk', 'scaling', scale)
            logger.info(f"DPI scaling set: {scale:.2f}")
        except Exception as e:
            logger.debug(f"DPI scaling設定エラー: {e}")

    def apply_custom_style(self):
        """ttk スタイル調整で GUI をよりクリアにする"""
        try:
            style = ttk.Style(self.root)
            style.theme_use('clam')
            style.configure('TButton', background=THEME['button_bg'], foreground=THEME['fg_text'], borderwidth=0, padding=(8, 6), font=("Arial", 10))
            style.map('TButton', background=[('active', THEME['button_hover']), ('disabled', THEME['bg_panel'])])
            style.configure('TEntry', fieldbackground=THEME['button_bg'], foreground=THEME['fg_text'], font=("Arial", 11))
            style.configure('Horizontal.TProgressbar', troughcolor=THEME['bg_main'], background=THEME['accent'], thickness=12)
        except Exception as e:
            logger.warning(f"スタイル適用エラー: {e}")
    
    def toggle_touch_mode(self):
        """タッチスクリーン用表示を切り替える"""
        self.touch_mode = not self.touch_mode
        self.touch_mode_button.config(text=f"タッチモード: {'ON' if self.touch_mode else 'OFF'}")
        self.apply_touch_mode()
        logger.info(f"タッチモード {'ON' if self.touch_mode else 'OFF'}")
    
    def apply_touch_mode(self):
        """タッチスクリーン向けにUIを拡大する"""
        if self.touch_mode:
            button_font = ("Arial", 12)
            label_font = ("Arial", 12)
            page_font = ("Arial", 12)
            entry_width = 10
            borderwidth = 2
        else:
            button_font = ("Arial", 10)
            label_font = ("Arial", 10)
            page_font = ("Arial", 11)
            entry_width = 8
            borderwidth = 0

        self.title_label.config(font=("Arial", 16, "bold") if self.touch_mode else ("Arial", 14, "bold"))
        self.folder_label.config(font=("Arial", 11) if self.touch_mode else ("Arial", 10))
        self.page_info.config(font=page_font)
        self.page_label.config(font=label_font)
        self.page_input.config(font=page_font, width=entry_width, bd=borderwidth)

        for button in self.touch_buttons:
            try:
                button.config(style='TButton')
                button.config(font=button_font)
            except Exception:
                pass

        self.chapter_listbox.config(font=("Arial", 11) if self.touch_mode else ("Arial", 9))
        self.image_label.config(borderwidth=borderwidth)

    def on_closing(self):
        """終了処理"""
        try:
            logger.info("アプリケーション終了処理開始")
            self.save_last_position()
            self.clear_image_cache()
            logger.info("アプリケーション終了")
        except Exception as e:
            logger.error(f"終了処理エラー: {e}")
        finally:
            self.root.destroy()

if __name__ == "__main__":
    enable_windows_dpi_awareness()
    root = tk.Tk()
    app = ComicReader(root)
    root.mainloop()
