import { createRouter, createWebHistory } from "vue-router";
import ChatWindow from "@/components/ChatWindow.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [{ path: "/", name: "chat", component: ChatWindow }],
});

export default router;
