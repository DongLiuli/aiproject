import { createRouter, createWebHistory } from 'vue-router'
import HomePage from '@/pages/HomePage.vue'
import SearchPage from '@/pages/SearchPage.vue'
import PaperDetailPage from '@/pages/PaperDetailPage.vue'
import ComparePage from '@/pages/ComparePage.vue'
import GraphPage from '@/pages/GraphPage.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/search'
    },
    {
      path: '/search',
      name: 'search',
      component: SearchPage
    },
    {
      path: '/library',
      name: 'library',
      component: HomePage
    },
    {
      path: '/papers/:id',
      name: 'paper-detail',
      component: PaperDetailPage
    },
    {
      path: '/compare',
      name: 'compare',
      component: ComparePage
    },
    {
      path: '/graph',
      name: 'graph',
      component: GraphPage
    }
  ]
})

export default router
