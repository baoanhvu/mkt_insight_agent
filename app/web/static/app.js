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
    chatStage: null,
    chatProgress: 0,
    chatBusy: false,
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
      const history = this.messages
        .filter((m) => !m.pending && !m.error)
        .map((m) => ({ role: m.role, content: m.content }));
      this.messages.push({ role: "user", content: text });
      this.draft = "";

      const reply = { role: "assistant", content: "", pending: true, trust: null };
      this.messages.push(reply);
      this.scrollChatToBottom();

      // Khong await: cho phep gui nhieu cau hoi lien tiep ma khong bi chan -
      // moi luot chay doc lap, chi cap nhat CHINH bubble `reply` cua no.
      streamChat(text, history, {
        onStage: (d) => {
          this.chatStage = d.label;
          this.chatProgress = d.progress;
          this.chatBusy = true;
        },
        onBlock: (d) => {
          if (d.verified) {
            reply.content += (reply.content ? "\n\n" : "") + d.md;
          } else {
            reply.content +=
              (reply.content ? "\n\n" : "") +
              "[Đoạn này bị giữ lại vì không đối chiếu được với dữ liệu nguồn]";
          }
          this.scrollChatToBottom();
        },
        onVerified: (d) => {
          reply.trust = d;
        },
        onDone: () => {
          reply.pending = false;
          this.chatBusy = false;
          this.chatStage = null;
          if (!reply.content) {
            reply.content = "Không tạo được câu trả lời cho câu hỏi này.";
          }
          this.scrollChatToBottom();
        },
        onError: (d) => {
          reply.pending = false;
          reply.error = true;
          this.chatBusy = false;
          this.chatStage = null;
          reply.content = reply.content || `Có lỗi khi xử lý câu hỏi: ${d.message || d.code}`;
          this.scrollChatToBottom();
        },
      });
    },

    scrollChatToBottom() {
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
