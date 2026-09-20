// Trang quan tri prompt (docs/07-prompt-fewshot.md muc 7.5). Goi /api/admin/*
// voi header X-Admin-Token lay tu query string cua chinh trang nay.

function adminPrompts(token) {
  return {
    token,
    prompts: [],
    selected: null,
    version: "",
    content: "",
    message: "",
    messageIsError: false,

    async init() {
      const res = await fetch("/api/admin/prompts", { headers: { "X-Admin-Token": this.token } });
      this.prompts = res.ok ? await res.json() : [];
    },

    async select(id) {
      this.selected = id;
      this.message = "";
      const res = await fetch(`/api/admin/prompts/${id}`, {
        headers: { "X-Admin-Token": this.token },
      });
      if (!res.ok) {
        this.message = `Không tải được prompt (HTTP ${res.status})`;
        this.messageIsError = true;
        return;
      }
      const data = await res.json();
      this.content = data.content;
      this.version = data.version;
    },

    async validateOnly() {
      const res = await fetch(`/api/admin/prompts/${this.selected}/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Token": this.token },
        body: JSON.stringify({ content: this.content }),
      });
      const data = await res.json().catch(() => ({ valid: false, errors: [String(res.status)] }));
      this.messageIsError = !data.valid;
      this.message = data.valid ? "Hợp lệ - có thể Lưu." : `Lỗi: ${JSON.stringify(data.errors)}`;
    },

    async save() {
      const res = await fetch(`/api/admin/prompts/${this.selected}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Admin-Token": this.token },
        body: JSON.stringify({ content: this.content }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        this.message = `Lưu thất bại: ${JSON.stringify(data.detail || data)}`;
        this.messageIsError = true;
        return;
      }
      this.version = data.version;
      this.message = `Đã lưu, phiên bản mới: ${data.version}`;
      this.messageIsError = false;
    },
  };
}
