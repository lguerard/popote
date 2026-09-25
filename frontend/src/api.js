import axios from 'axios'

export const api = axios.create({ baseURL: '/api' })

// Le jeton est posé une fois pour toutes sur l'instance : chaque appel
// existant le porte sans avoir à être modifié.
export function setAuthToken(token) {
  if (token) api.defaults.headers.common.Authorization = `Bearer ${token}`
  else delete api.defaults.headers.common.Authorization
}

export const register = (data) => api.post('/auth/register', data).then(r => r.data)
export const login = (data) => api.post('/auth/login', data).then(r => r.data)
export const listUsers = (includeArchived = false) =>
  api.get('/auth/users', { params: { include_archived: includeArchived } }).then(r => r.data)
export const approveUser = (id) => api.post(`/auth/users/${id}/approve`).then(r => r.data)
export const rejectUser = (id) => api.post(`/auth/users/${id}/reject`).then(r => r.data)

export const getRecipes = (params) => api.get('/recipes', { params }).then(r => r.data)
export const getRecipe = (id) => api.get(`/recipes/${id}`).then(r => r.data)
export const createRecipe = (data) => api.post('/recipes', data).then(r => r.data)
export const updateRecipe = (id, data) => api.put(`/recipes/${id}`, data).then(r => r.data)
export const deleteRecipe = (id) => api.delete(`/recipes/${id}`)
export const toggleFavorite = (id) => api.post(`/recipes/${id}/favorite`).then(r => r.data)
export const analyzeNutrition = (id) => api.post(`/recipes/${id}/nutrition`).then(r => r.data)
export const uploadThumbnail = (id, file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post(`/recipes/${id}/thumbnail`, form, { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data)
}
export const generateThumbnail = (id) => api.post(`/recipes/${id}/thumbnail/generate`).then(r => r.data)
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

// Historique et avis
export const patchRecipe = (id, data) => api.patch(`/recipes/${id}`, data).then(r => r.data)
export const markCooked = (id, data = {}) => api.post(`/recipes/${id}/cooked`, data).then(r => r.data)
export const getCookHistory = (id) => api.get(`/recipes/${id}/history`).then(r => r.data)
export const deleteCookLog = (id, logId) => api.delete(`/recipes/${id}/history/${logId}`).then(r => r.data)

// Réextraction, partage
export const reextractRecipe = (id) => api.post(`/recipes/${id}/reextract`).then(r => r.data)
export const shareRecipe = (id) => api.post(`/recipes/${id}/share`).then(r => r.data)
export const unshareRecipe = (id) => api.delete(`/recipes/${id}/share`).then(r => r.data)

// « Qu'est-ce que je cuisine ? »
export const whatToCook = (data) => api.post('/recipes/what-to-cook', data).then(r => r.data)

// Carnets
export const getCollections = (recipeId) =>
  api.get('/collections', { params: recipeId ? { recipe_id: recipeId } : {} }).then(r => r.data)
export const getCollection = (id) => api.get(`/collections/${id}`).then(r => r.data)
export const createCollection = (data) => api.post('/collections', data).then(r => r.data)
export const updateCollection = (id, data) => api.patch(`/collections/${id}`, data).then(r => r.data)
export const deleteCollection = (id) => api.delete(`/collections/${id}`)
export const addToCollection = (id, recipeId) => api.put(`/collections/${id}/recipes/${recipeId}`)
export const removeFromCollection = (id, recipeId) => api.delete(`/collections/${id}/recipes/${recipeId}`)
export const shareCollection = (id) => api.post(`/collections/${id}/share`).then(r => r.data)
export const unshareCollection = (id) => api.delete(`/collections/${id}/share`).then(r => r.data)

// Liste de courses persistée
export const getShoppingItems = () => api.get('/shopping/items').then(r => r.data)
export const generateShoppingItems = (data) => api.post('/shopping/items/generate', data).then(r => r.data)
export const addShoppingItem = (data) => api.post('/shopping/items', data).then(r => r.data)
export const updateShoppingItem = (id, data) => api.patch(`/shopping/items/${id}`, data).then(r => r.data)
export const deleteShoppingItem = (id) => api.delete(`/shopping/items/${id}`)
export const clearShoppingItems = (onlyChecked) =>
  api.delete('/shopping/items', { params: { only_checked: onlyChecked } })
export const shareShoppingList = () => api.post('/shopping/share').then(r => r.data)
export const unshareShoppingList = () => api.delete('/shopping/share').then(r => r.data)

// Pages publiques : instance sans jeton, pour ne jamais envoyer celui de
// la personne connectée sur un lien qu'on lui a partagé.
const publicApi = axios.create({ baseURL: '/api/public' })
export const getPublicRecipe = (token) => publicApi.get(`/recipes/${token}`).then(r => r.data)
export const getPublicCollection = (token) => publicApi.get(`/collections/${token}`).then(r => r.data)
export const getPublicCollectionRecipe = (token, id) =>
  publicApi.get(`/collections/${token}/recipes/${id}`).then(r => r.data)
export const getPublicShopping = (token) => publicApi.get(`/shopping/${token}`).then(r => r.data)
export const checkPublicShoppingItem = (token, id, checked) =>
  publicApi.patch(`/shopping/${token}/items/${id}`, { checked }).then(r => r.data)

export const publicLink = (path) => `${window.location.origin}${path}`
