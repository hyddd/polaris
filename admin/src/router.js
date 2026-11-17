import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'chat', component: () => import('./views/ChatView.vue') },
  { path: '/sessions', name: 'sessions', component: () => import('./views/SessionsView.vue') },
  { path: '/config', name: 'config', component: () => import('./views/ConfigView.vue') },
  { path: '/calendar', name: 'calendar', component: () => import('./views/CalendarView.vue') },
  { path: '/todos', name: 'todos', component: () => import('./views/TodosView.vue') },
  { path: '/notes', name: 'notes', component: () => import('./views/NotesView.vue') },
  { path: '/knowledge', name: 'knowledge', component: () => import('./views/KnowledgeView.vue') },
  { path: '/reminders', name: 'reminders', component: () => import('./views/RemindersView.vue') },
  { path: '/notify', name: 'notify', component: () => import('./views/NotifyView.vue') },
  { path: '/status', name: 'status', component: () => import('./views/StatusView.vue') },
]

export default createRouter({
  history: createWebHistory('/'),
  routes,
})
