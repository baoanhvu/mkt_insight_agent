function dashboardApp() {
  return {
    tab: "campaign",
    tabs: [
      { id: "campaign", label: "Chiến dịch" },
      { id: "persona", label: "Chân dung KH" },
      { id: "actions", label: "Hành động CLV" },
      { id: "chat", label: "Hỏi đáp" },
    ],
    ready: true,
    summary: {},
    campaigns: [],
    funnel: { stages: [], steps: [], caveat_vi: "" },
    trend: [],
    segments: [],
    actions: [],
    draft: "",
    messages: [],
    evidencePanelOpen: false,
    evidenceTraceId: "",
    evidenceFacts: [],

    async init() {
      try {
        const [ready, summary, campaigns, funnel, trend, segmentsResp, actions] =
          await Promise.all([
            fetch("/readyz").then((r) => r.json()),
            fetch("/api/dashboard/summary").then((r) => r.json()),
            fetch("/api/dashboard/campaigns").then((r) => r.json()),
            fetch("/api/dashboard/funnel").then((r) => r.json()),
            fetch("/api/dashboard/trend").then((r) => r.json()),
            fetch("/api/segments").then((r) => r.json()),
            fetch("/api/actions").then((r) => r.json()),
          ]);
        this.ready = ready.status === "ok";
        this.summary = summary;
        this.campaigns = campaigns;
        this.funnel = funnel;
        this.trend = trend;
        this.segments = segmentsResp.segments || [];
        this.actions = actions;

        this.$nextTick(() => {
          renderRomiChart("chart-romi", this.campaigns);
          renderFunnelChart("chart-funnel", this.funnel.stages);
          renderTrendChart("chart-trend", this.trend);
        });
      } catch (e) {
        this.ready = false;
        console.error("khong tai duoc du lieu dashboard", e);
      }
    },

    sendChat() {
      const text = this.draft.trim();
      if (!text) return;
      this.messages.push({ role: "user", content: text });
      this.draft = "";
      // Chat day du (goi /api/chat qua SSE) den o giai doan tich hop LLM
      // (T10). Hien tai chi echo lai de khung hoi thoai co noi dung thuc su
      // khi kiem tra rang buoc 60vh.
      this.messages.push({
        role: "assistant",
        content: "Hỏi đáp tự do sẽ khả dụng khi tích hợp LLM ở giai đoạn sau.",
      });
      this.$nextTick(() => {
        const el = document.getElementById("chat-scroll");
        if (el) el.scrollTop = el.scrollHeight;
      });
    },

    openEvidence(traceId, facts) {
      this.evidenceTraceId = traceId;
      this.evidenceFacts = facts || [];
      this.evidencePanelOpen = true;
    },
  };
}
