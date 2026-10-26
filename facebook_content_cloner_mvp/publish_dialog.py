"""Hộp thoại đăng bài đã duyệt lên Page đang chọn (chữ / ảnh / video, có thể hẹn giờ)."""
import queue
import threading
from pathlib import Path
from tkinter import BooleanVar, StringVar, Text, Toplevel, filedialog, messagebox, ttk
from typing import Callable

import publisher
from pages import PageProfile


class PublishDialog(Toplevel):
    def __init__(self, parent, profile: PageProfile, post_id: str, source: str, text: str, media_root: Path,
                 do_send: Callable[[publisher.PublishPlan], str], on_done: Callable[[str], None]):
        super().__init__(parent)
        self.profile, self.post_id, self.source, self.text = profile, post_id, source, text
        self.media_root, self.do_send, self.on_done = media_root, do_send, on_done
        self.title(f'Đăng lên Page — {profile.name}')
        self.geometry('720x620')
        self.transient(parent)

        body = ttk.Frame(self, padding=12)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text=f'Đăng lên: {profile.name}', font=('Segoe UI', 11, 'bold')).pack(anchor='w')
        ttk.Label(body, text='Nội dung sẽ đăng:').pack(anchor='w', pady=(8, 0))
        preview = Text(body, height=14, wrap='word')
        preview.insert('1.0', text)
        preview.configure(state='disabled')
        preview.pack(fill='both', expand=True)

        self.media_var = StringVar()
        row = ttk.Frame(body)
        row.pack(fill='x', pady=(8, 0))
        ttk.Label(row, text='Ảnh/Video đính kèm:').pack(side='left')
        ttk.Entry(row, textvariable=self.media_var).pack(side='left', fill='x', expand=True, padx=4)
        ttk.Button(row, text='Chọn…', command=self.pick_media).pack(side='left')
        ttk.Button(row, text='✕', width=3, command=lambda: self.media_var.set('')).pack(side='left', padx=(2, 0))
        self.own_media_var = BooleanVar(value=False)
        ttk.Checkbutton(body, text='Tôi có quyền dùng file này (bắt buộc nếu file nằm trong thư mục media cào về)',
                        variable=self.own_media_var).pack(anchor='w', pady=(4, 0))

        self.schedule_var = StringVar()
        row2 = ttk.Frame(body)
        row2.pack(fill='x', pady=(8, 0))
        ttk.Label(row2, text='Hẹn giờ (để trống = đăng ngay):').pack(side='left')
        ttk.Entry(row2, textvariable=self.schedule_var, width=20).pack(side='left', padx=4)
        ttk.Label(row2, text='vd 2026-10-27T20:00 (giờ VN)', foreground='gray').pack(side='left')

        self.status_lbl = ttk.Label(body, text='', foreground='#c00')
        self.status_lbl.pack(anchor='w', pady=(8, 0))
        bar = ttk.Frame(body)
        bar.pack(fill='x', pady=(8, 0))
        self.publish_btn = ttk.Button(bar, text='🚀 Đăng', command=self.submit)
        self.publish_btn.pack(side='left')
        ttk.Button(bar, text='Hủy', command=self.destroy).pack(side='right')

        if not profile.fb_page_id or not profile.fb_page_token:
            self.publish_btn.configure(state='disabled')
            self.status_lbl.configure(text='Chưa cấu hình ID/token cho Page này (⚙️ Quản lý Page).')
        try:
            self.grab_set()
        except Exception:
            pass

    def pick_media(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[
            ('Ảnh/Video', '*.jpg *.jpeg *.png *.webp *.mp4 *.mov'), ('Tất cả', '*.*')])
        if path:
            self.media_var.set(path)

    def submit(self):
        try:
            plan = publisher.prepare(self.source, self.text, self.profile.max_similarity,
                                     self.media_var.get().strip() or None, self.media_root,
                                     self.schedule_var.get().strip() or None,
                                     i_own_media=self.own_media_var.get())
        except publisher.PublishError as e:
            messagebox.showerror('Không đăng được', str(e), parent=self)
            return
        when = f'hẹn lúc {self.schedule_var.get().strip()}' if plan.scheduled_ts else 'NGAY BÂY GIỜ'
        kind = {'text': 'chữ', 'photo': 'kèm ảnh', 'video': 'video'}[plan.kind]
        if not messagebox.askyesno('Xác nhận đăng',
                                   f'Đăng bài ({kind}) lên "{self.profile.name}" {when}?\n'
                                   'Bài sẽ hiển thị công khai.', parent=self):
            return
        self.publish_btn.configure(state='disabled')
        self.status_lbl.configure(text='Đang đăng…', foreground='#0066cc')

        results: queue.Queue = queue.Queue()

        def work():  # luồng phụ: không chạm vào Tk, chỉ gửi kết quả về hàng đợi
            try:
                results.put(('ok', self.do_send(plan)))
            except Exception as e:
                results.put(('err', str(e)))

        def poll():
            try:
                status, value = results.get_nowait()
            except queue.Empty:
                self.after(100, poll)
                return
            (self._done if status == 'ok' else self._failed)(value)

        threading.Thread(target=work, daemon=True).start()
        self.after(100, poll)

    def _failed(self, msg):
        self.publish_btn.configure(state='normal')
        self.status_lbl.configure(text=msg, foreground='#c00')
        messagebox.showerror('Đăng thất bại', msg, parent=self)

    def _done(self, fb_id):
        self.on_done(fb_id)
        self.destroy()
