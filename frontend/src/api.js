import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export const getRecipes = (params) => api.get('/recipes', { params }).then(r => r.data)
export const getRecipe = (id) => api.get(`/recipes/${id}`).then(r => r.data)
export const createRecipe = (data) => api.post('/recipes', data).then(r => r.data)
export const updateRecipe = (id, data) => api.put(`/recipes/${id}`, data).then(r => r.data)
export const deleteRecipe = (id) => api.delete(`/recipes/${id}`)
export const toggleFavorite = (id) => api.post(`/recipes/${id}/favorite`).then(r => r.data)
export const analyzeNutrition = (id) => api.post(`/recipes/${id}/nutrition`).then(r => r.data)
export const submitExtraction = (input) => api.post('/extract', { input }).then(r => r.data)
export const submitImageExtraction = (file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/extract/image', form, { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data)
}
export const getTaskStatus = (id) => api.get(`/tasks/${id}`).then(r => r.data)
export const getShoppingList = (recipe_ids) => api.post('/shopping-list', { recipe_ids }).then(r => r.data)
export const getMealPlans = (params) => api.get('/meal-plans', { params }).then(r => r.data)
export const createMealPlan = (data) => api.post('/meal-plans', data).then(r => r.data)
export const deleteMealPlan = (id) => api.delete(`/meal-plans/${id}`)
export const getAchievements = () => api.get('/achievements').then(r => r.data)
export const trackCookingMode = () => api.post('/achievements/cooking-mode').catch(() => {})
