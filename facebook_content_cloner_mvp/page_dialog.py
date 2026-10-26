"""Hộp thoại quản lý nhiều Facebook Page: thông tin, token, AI, hashtag, prompt riêng."""
from tkinter import END, Listbox, StringVar, Text, Toplevel, messagebox, ttk
from typing import Callable

from pages import (DEFAULT_SLUG, GENERIC_ANALYSIS_PROMPT, GENERIC_CREATION_PROMPT, NHAN_TAM_CREATION_PROMPT,
                   PageProfile, PageStore)

DEFAULT_PROVIDER_LABEL = '(dùng mặc định chung)'
PROVIDER_LABELS = [DEFAULT_PROVIDER_LABEL, 'gemini', 'cloudflare', 'openai']


class PageManagerDialog(Toplevel):
    def __init__(self, parent, store: PageStore, test_token: Callable[[str, str], str],
                 on_saved: Callable[[str], None]):
        super().__init__(parent)
        self.store = store
        self.test_token = test_token
        self.on_saved = on_saved
        self.current_slug: str | None = None
        self.title('Quản lý Page')
        self.geometry('980x720')
        self.transient(parent)

        left = ttk.Frame(self, padding=10)
        left.pack(side='left', fill='y')
        ttk.Label(left, text='Các Page', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.listbox = Listbox(left, width=28, height=20, exportselection=False)
        self.listbox.pack(fill='y', expand=True, pady=4)
        self.listbox.bind('<<ListboxSelect>>', self._on_select)
        ttk.Button(left, text='＋ Page mới', command=self.new_page).pack(fill='x', pady=2)
        ttk.Button(left, text='🗑 Xóa Page', command=self.delete_page).pack(fill='x', pady=2)

        right = ttk.Frame(self, padding=(4, 10, 10, 10))
        right.pack(side='left', fill='both', expand=True)
        self.vars = {k: StringVar() for k in
                     ('name', 'fb_page_id', 'fb_page_token', 'provider', 'hashtags', 'max_similarity')}
        form = ttk.Frame(right)
        form.pack(fill='x')
        form.columnconfigure(1, weight=1)
        rows = [('Tên Page', 'name', {}), ('Facebook Page ID (số)', 'fb_page_id', {}),
                ('Page Access Token', 'fb_page_token', {'show': '●'}), ('Hashtag mặc định', 'hashtags', {}),
                ('Ngưỡng trùng tối đa (0–1)', 'max_similarity', {})]
        for i, (label, key, opts) in enumerate(rows):
            ttk.Label(form, text=label + ':').grid(row=i, column=0, sticky='w', pady=2)
            ttk.Entry(form, textvariable=self.vars[key], **opts).grid(row=i, column=1, sticky='ew', pady=2)
        ttk.Label(form, text='Nhà cung cấp AI:').grid(row=len(rows), column=0, sticky='w', pady=2)
        ttk.Combobox(form, textvariable=self.vars['provider'], values=PROVIDER_LABELS,
                     state='readonly', width=26).grid(row=len(rows), column=1, sticky='w', pady=2)
        ttk.Button(form, text='🔍 Kiểm tra token', command=self.check_token).grid(row=2, column=2, padx=6)

        ttk.Label(right, text='Dùng {page_name}, {hashtags} trong prompt để chèn tên Page và hashtag.',
                  foreground='gray').pack(anchor='w', pady=(8, 0))
        self.analysis_text = self._prompt_box(right, 'Prompt phân tích bài nguồn:')
        self.creation_text = self._prompt_box(right, 'Prompt sáng tạo bài mới:')

        bar = ttk.Frame(right)
        bar.pack(fill='x', pady=(8, 0))
        ttk.Button(bar, text='💾 Lưu', command=self.save).pack(side='left')
        ttk.Button(bar, text='↺ Khôi phục prompt mặc định', command=self.reset_prompts).pack(side='left', padx=6)
        ttk.Button(bar, text='Đóng', command=self.destroy).pack(side='right')

        self._reload_list(self.store.active().slug)
        try:
            self.grab_set()
        except Exception:
            pass  # cửa sổ chưa hiển thị (vd khi chạy test)

    # ---- dựng giao diện ----
    @staticmethod
    def _prompt_box(parent, label):
        ttk.Label(parent, text=label, font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(6, 0))
        box = ttk.Frame(parent)
        box.pack(fill='both', expand=True)
        text = Text(box, height=8, wrap='word')
        bar = ttk.Scrollbar(box, orient='vertical', command=text.yview)
        text.configure(yscrollcommand=bar.set)
        text.pack(side='left', fill='both', expand=True)
        bar.pack(side='right', fill='y')
        return text

    def _reload_list(self, select_slug):
        self.listbox.delete(0, END)
        pages = self.store.list()
        for p in pages:
            self.listbox.insert(END, p.name)
        idx = next((i for i, p in enumerate(pages) if p.slug == select_slug), 0)
        self.listbox.selection_clear(0, END)
        self.listbox.selection_set(idx)
        self._fill(pages[idx])

    def _fill(self, p: PageProfile):
        self.current_slug = p.slug or None
        for key in ('name', 'fb_page_id', 'fb_page_token', 'hashtags'):
            self.vars[key].set(getattr(p, key))
        self.vars['max_similarity'].set(str(p.max_similarity))
        self.vars['provider'].set(p.provider or DEFAULT_PROVIDER_LABEL)
        for box, value in ((self.analysis_text, p.analysis_prompt), (self.creation_text, p.creation_prompt)):
            box.delete('1.0', END)
            box.insert('1.0', value)

    def _form_profile(self) -> PageProfile:
        try:
            sim = float(self.vars['max_similarity'].get().strip().replace(',', '.'))
        except ValueError:
            raise ValueError('Ngưỡng trùng phải là số, ví dụ 0.35.') from None
        provider = self.vars['provider'].get()
        return PageProfile(
            slug=self.current_slug or '', name=self.vars['name'].get(),
            fb_page_id=self.vars['fb_page_id'].get(), fb_page_token=self.vars['fb_page_token'].get(),
            provider='' if provider == DEFAULT_PROVIDER_LABEL else provider,
            hashtags=self.vars['hashtags'].get().strip(),
            analysis_prompt=self.analysis_text.get('1.0', 'end-1c').strip(),
            creation_prompt=self.creation_text.get('1.0', 'end-1c').strip(), max_similarity=sim)

    def _is_dirty(self) -> bool:
        try:
            form = self._form_profile()
        except ValueError:
            return True
        if not self.current_slug:
            return bool(form.name.strip())
        try:
            stored = self.store.get(self.current_slug)
        except KeyError:
            return True
        form.name = form.name.strip()
        return form != stored

    # ---- hành động ----
    def new_page(self):
        self.listbox.selection_clear(0, END)
        self._fill(PageProfile(slug='', name=''))

    def reset_prompts(self):
        creation = NHAN_TAM_CREATION_PROMPT if self.current_slug == DEFAULT_SLUG else GENERIC_CREATION_PROMPT
        for box, value in ((self.analysis_text, GENERIC_ANALYSIS_PROMPT), (self.creation_text, creation)):
            box.delete('1.0', END)
            box.insert('1.0', value)

    def save(self) -> bool:
        try:
            profile = self._form_profile()
            self.store.save(profile)
        except ValueError as e:
            messagebox.showerror('Không lưu được', str(e), parent=self)
            return False
        self._reload_list(profile.slug)
        self.on_saved(profile.slug)
        return True

    def delete_page(self):
        if not self.current_slug:
            return
        name = self.store.get(self.current_slug).name
        if not messagebox.askyesno('Xóa Page', f'Xóa cấu hình Page "{name}"?\n'
                                   'Nháp đã viết cho Page này vẫn còn trong dữ liệu.', parent=self):
            return
        try:
            self.store.delete(self.current_slug)
        except ValueError as e:
            messagebox.showerror('Không xóa được', str(e), parent=self)
            return
        self._reload_list(self.store.active().slug)
        self.on_saved(self.store.active().slug)

    def check_token(self):
        pid = self.vars['fb_page_id'].get().strip()
        tok = self.vars['fb_page_token'].get().strip()
        if not pid or not tok:
            messagebox.showwarning('Thiếu thông tin', 'Nhập Page ID và token trước.', parent=self)
            return
        try:
            name = self.test_token(pid, tok)
            messagebox.showinfo('Token hợp lệ', f'Kết nối được Page: {name}', parent=self)
        except Exception as e:
            messagebox.showerror('Token lỗi', str(e), parent=self)

    def _on_select(self, event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        target = self.store.list()[sel[0]]
        if target.slug == self.current_slug:
            return
        if self._is_dirty() and messagebox.askyesno('Chưa lưu', 'Lưu thay đổi của Page đang sửa?', parent=self):
            if not self.save():
                return
        self._reload_list(target.slug)
