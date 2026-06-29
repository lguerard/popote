package com.kitchenai.data

data class Achievement(
    val id: String,
    val name: String,
    val description: String,
    val icon: String,
    val progress: Int,
    val goal: Int,
    val unlocked_at: String?,
    val category: String,
) {
    val isUnlocked get() = unlocked_at != null
    val progressFraction get() = if (goal > 0) progress.toFloat() / goal else 1f
}
