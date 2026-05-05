import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'chat', component: () => import('./views/ChatView.vue') },
  { path: '/sessions', name: 'sessions', component: () => import('./views/SessionsView.vue') },
  { path: '/config', name: 'config', component: () => import('./views/ConfigView.vue') },
  { path: '/data', name: 'data', component: () => import('./views/DataView.vue') },
  { path: '/notes', name: 'notes', component: () => import('./views/NotesView.vue') },
]

export default createRouter({
  history: createWebHistory('/'),
  routes,
})
