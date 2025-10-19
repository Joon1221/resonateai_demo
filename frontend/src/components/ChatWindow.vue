<template>
  <div class="chat">
    <header class="chat__header">
    </header>

    <main class="chat__messages" ref="scrollEl">
      <div v-for="(m,i) in visibleMessages" :key="i" :class="['msg', m.role]">
        <div class="msg__bubble">{{ m.content }}</div>
      </div>
      <div v-if="loading" class="msg assistant">
        <div class="msg__bubble">…thinking</div>
      </div>
    </main>

    <footer class="chat__composer">
      <form @submit.prevent="send()">
        <input v-model="draft" placeholder="Type your message…" :disabled="loading" />
        <button :disabled="loading || !draft.trim()">Send</button>
      </form>

    </footer>
  </div>
</template>

<script setup>
import { ref, nextTick, watch, onMounted, computed } from "vue";
import { postChat } from "@/api/chat";

const flow = ref("new_patient");
const messages = ref([]);
const draft = ref("");
const loading = ref(false);
const scrollEl = ref(null);

function scrollToBottom() {
  nextTick(() => {
    if (scrollEl.value) scrollEl.value.scrollTo({ top: 999999, behavior: "smooth" });
  });
}

function lastAssistant() {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    if (messages.value[i].role === "assistant") return messages.value[i].content || "";
  }
  return "";
}

function askedNewOrExisting(txt) {
  const s = (txt || "").toLowerCase();
  return /new\s+patient|existing\s+patient/.test(s) || /new or existing/.test(s);
}

// initial assistant menu (no server call needed)
const MENU_TEXT =
  "Hi, this is DentalBot, your virtual assistant! How can I help today? \n1) Book appointment\n2) Change appointment\n3) General inquiry\nPlease choose one.";

onMounted(() => {
  if (messages.value.length === 0) {
    messages.value.push({ role: "assistant", content: MENU_TEXT });
  }
});

// computed UI states
const showStartMenu = computed(() => messages.value.length === 1 && messages.value[0].role === "assistant" && messages.value[0].content === MENU_TEXT);

const showNewExisting = computed(() => {
  // show if user chose Book appointment OR assistant is asking new/existing
  const choseBook = messages.value.some(m => m.role === "user" && /book appointment/i.test(m.content));
  return choseBook || askedNewOrExisting(lastAssistant());
});

// Only render user messages + the last assistant message per post-call (keep full chain in `messages`)
const visibleMessages = computed(() => {
  const arr = messages.value;
  const out = [];
  const n = arr.length;
  if (n === 0) return out;

  // find index of first user message
  const firstUserIdx = arr.findIndex(m => m.role === "user");

  // If there are no user messages, show only the last assistant (initial menu case)
  if (firstUserIdx === -1) {
    let lastAssistantIndex = -1;
    for (let i = 0; i < n; i++) if (arr[i].role === "assistant") lastAssistantIndex = i;
    if (lastAssistantIndex !== -1) out.push(arr[lastAssistantIndex]);
    return out;
  }

  // Include the last assistant before the first user (if any)
  let lastLeadAssistant = -1;
  for (let i = 0; i < firstUserIdx; i++) {
    if (arr[i].role === "assistant") lastLeadAssistant = i;
  }
  if (lastLeadAssistant !== -1) out.push(arr[lastLeadAssistant]);

  // For each user message include the user and the last assistant that follows it (up to the next user)
  for (let i = firstUserIdx; i < n; i++) {
    if (arr[i].role !== "user") continue;
    out.push(arr[i]);
    let lastAssistantAfterUser = -1;
    for (let j = i + 1; j < n && arr[j].role !== "user"; j++) {
      if (arr[j].role === "assistant") lastAssistantAfterUser = j;
    }
    if (lastAssistantAfterUser !== -1) out.push(arr[lastAssistantAfterUser]);
  }

  return out;
});

async function send(text) {
  const content = (text ?? draft.value).trim();
  if (!content) return;
  messages.value.push({ role: "user", content });
  draft.value = "";
  loading.value = true;
  scrollToBottom();
  try {
    const res = await postChat(flow.value, messages.value);

    // If server provided an assistant_chain, append each assistant message (chain-of-thought)
    if (Array.isArray(res.assistant_chain) && res.assistant_chain.length > 0) {
      for (const msg of res.assistant_chain) {
        // msg is expected to be { role: "assistant", content: "..." } or similar
        messages.value.push({ role: "assistant", content: msg.content ?? msg });
      }
    } else {
      // fallback to single reply
      const reply = res.reply ?? "Okay.";
      messages.value.push({ role: "assistant", content: reply });
    }
  } catch (e) {
    console.error(e);
    messages.value.push({ role: "assistant", content: "Sorry—something went wrong. Please try again." });
  } finally {
    loading.value = false;
    scrollToBottom();
  }
}

// reset conversation on explicit flow change via dropdown (optional)
watch(flow, (val, old) => {
  if (val !== old && messages.value.length > 0) {
    messages.value = [{ role: "assistant", content: MENU_TEXT }];
  }
});
</script>

<style scoped>
.chat { max-width: 760px; margin: 0 auto; display: grid; grid-template-rows: auto 1fr auto; height: 100dvh; }
.chat__header { padding: 12px; border-bottom: 1px solid #eee; display: flex; gap: 8px; align-items: center; }
.chat__flow { padding: 8px; }
.chat__messages { padding: 16px; overflow: auto; background: #fafafa; }
.msg { display: flex; margin-bottom: 10px; }
.msg.user { justify-content: flex-end; }
.msg.assistant { justify-content: flex-start; }
.msg__bubble { max-width: 75%; padding: 10px 12px; border-radius: 12px; white-space: pre-wrap; }
.msg.user .msg__bubble { background: #2266ff; color: white; border-bottom-right-radius: 4px; }
.msg.assistant .msg__bubble { background: white; border: 1px solid #e5e5e5; border-bottom-left-radius: 4px; }
.chat__composer { padding: 12px; border-top: 1px solid #eee; display: grid; gap: 8px; }
.chat__composer form { display: grid; grid-template-columns: 1fr auto; gap: 8px; }
.chat__composer input { padding: 10px; border: 1px solid #ddd; border-radius: 8px; }
.chat__composer button { padding: 10px 14px; border: none; border-radius: 8px; background: #2266ff; color: white; }
.chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.chips button { background: #f1f4ff; color: #1c3fb7; border: 1px solid #dfe7ff; padding: 8px 10px; border-radius: 8px; }
</style>
