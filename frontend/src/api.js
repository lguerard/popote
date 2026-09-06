import axios from 'axios'

// withCredentials : le cookie de session httpOnly posé par /api/auth/login
// accompagne chaque requête. L'app est servie par le même nginx que l'API,
// donc c'est bien du same-origin.
const api = axios.create({ baseURL: '/api', withCredentials: true })

// Un 401 signifie « session expirée ou absente ». On prévient l'app plutôt que
// de laisser chaque écran afficher une erreur réseau incompréhensible.
let onUnauthorized = () => {}
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn }

api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401) onUnauthorized()
    return Promise.reject(error)
  },
)

// Remonte le message d'erreur du backend ("Mot de passe actuel incorrect")
// plutôt que le « Request failed with status code 400 » d'axios.
export const messageErreur = (error, repli = 'Une erreur est survenue') => {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  // Erreur de validation pydantic : liste de {msg, loc}
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  return repli
}

/* ------------------------------- comptes ------------------------------- */

export const getAuthStatus = () => api.get('/auth/status').then(r => r.data)
export const setupFirstAccount = (data) => api.post('/auth/setup', data).then(r => r.data)
export const login = (email, password) => api.post('/auth/login', { email, password }).then(r => r.data)
export const logout = () => api.post('/auth/logout')
export const changePassword = (current_password, new_password) =>
  api.post('/auth/change-password', { current_password, new_password })
export const checkResetToken = (token) => api.get(`/auth/reset/${token}`).then(r => r.data)
export const resetPassword = (token, new_password) =>
  api.post('/auth/reset', { token, new_password })
export const getUsers = () => api.get('/auth/users').then(r => r.data)
export const createUser = (data) => api.post('/auth/users', data).then(r => r.data)
export const createResetLink = (id) => api.post(`/auth/users/${id}/reset-link`).then(r => r.data)
export const setUserRole = (id, is_admin) => api.patch(`/auth/users/${id}/role`, { is_admin }).then(r => r.data)
export const deleteUser = (id) => api.delete(`/auth/users/${id}`)

/* ------------------------------- recettes ------------------------------ */

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
