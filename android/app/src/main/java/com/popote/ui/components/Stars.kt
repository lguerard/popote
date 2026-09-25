package com.popote.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val StarOn = Color(0xFFFBBF24)
private val StarOff = Color(0xFFD1D5DB)

/** Note de 1 à 5 ; sans onChange, affichage seul. */
@Composable
fun Stars(
    value: Int?,
    onChange: ((Int) -> Unit)? = null,
    size: TextUnit = 28.sp,
    modifier: Modifier = Modifier,
) {
    Row(modifier) {
        (1..5).forEach { n ->
            val clickable = if (onChange != null) Modifier.clickable { onChange(n) } else Modifier
            Text(
                "★",
                fontSize = size,
                color = if (value != null && n <= value) StarOn else StarOff,
                style = MaterialTheme.typography.bodyLarge,
                modifier = clickable.padding(horizontal = 2.dp),
            )
        }
    }
}
