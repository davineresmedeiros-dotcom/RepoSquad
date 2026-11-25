package com.reposquad.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { RepoSquadScreen() }
    }
}

@Composable
private fun RepoSquadScreen() {
    var repo by remember { mutableStateOf("") }
    var task by remember { mutableStateOf("") }
    var agents by remember { mutableIntStateOf(3) }
    var running by remember { mutableStateOf(false) }

    MaterialTheme {
        Scaffold { padding ->
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(24.dp),
                verticalArrangement = Arrangement.spacedBy(18.dp)
            ) {
                item {
                    Text("RepoSquad", style = MaterialTheme.typography.headlineLarge)
                    Text("Your AI coding squad", style = MaterialTheme.typography.bodyLarge)
                }
                item {
                    OutlinedTextField(
                        value = repo,
                        onValueChange = { repo = it },
                        label = { Text("GitHub repository (owner/repo)") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                }
                item {
                    Text("Gemini agents: $agents", style = MaterialTheme.typography.titleMedium)
                    Slider(
                        value = agents.toFloat(),
                        onValueChange = { agents = it.toInt().coerceIn(1, 5) },
                        valueRange = 1f..5f,
                        steps = 3
                    )
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        (1..5).forEach { Text("$it") }
                    }
                }
                item {
                    OutlinedTextField(
                        value = task,
                        onValueChange = { task = it },
                        label = { Text("What should your squad build?") },
                        modifier = Modifier.fillMaxWidth(),
                        minLines = 4
                    )
                }
                item {
                    Button(
                        onClick = { running = !running },
                        enabled = repo.contains("/") && task.isNotBlank(),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(if (running) "Stop squad" else "Start squad")
                    }
                    Text(
                        if (running) "Demo state only — backend connection is next."
                        else "Choose a repository and task to start.",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        }
    }
}
