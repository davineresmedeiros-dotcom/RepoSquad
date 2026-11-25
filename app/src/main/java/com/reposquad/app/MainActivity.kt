package com.reposquad.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URI


private fun isAllowedBackendUrl(value: String): Boolean = try {
    val uri = URI(value.trim())
    val scheme = uri.scheme?.lowercase()
    val host = uri.host?.lowercase()
    uri.userInfo == null && host != null && (scheme == "https" || (scheme == "http" && (host == "localhost" || host == "127.0.0.1")))
} catch (_: Exception) { false }

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { RepoSquadScreen() }
    }
}

private suspend fun apiRequest(base: String, token: String, path: String, method: String = "GET", body: JSONObject? = null): JSONObject =
    withContext(Dispatchers.IO) {
        val connection = (URL(base.trimEnd('/') + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 15000
            readTimeout = 20000
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Authorization", "Bearer $token")
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        try {
            if (body != null) connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (code !in 200..299) {
                val message = try { JSONObject(text).optString("detail", text) } catch (_: Exception) { text }
                throw IllegalStateException("HTTP $code: $message")
            }
            JSONObject(text)
        } finally {
            connection.disconnect()
        }
    }

@Composable
private fun RepoSquadScreen() {
    val context = LocalContext.current
    val prefs = remember { context.getSharedPreferences("reposquad_state", android.content.Context.MODE_PRIVATE) }
    var apiUrl by remember { mutableStateOf(prefs.getString("apiUrl", "") ?: "") }
    var apiToken by remember { mutableStateOf("") }
    var repo by remember { mutableStateOf(prefs.getString("repo", "") ?: "") }
    var task by remember { mutableStateOf(prefs.getString("task", "") ?: "") }
    var agents by remember { mutableIntStateOf(prefs.getInt("agents", 3).coerceIn(1, 5)) }
    var jobId by remember { mutableStateOf(prefs.getString("jobId", "") ?: "") }
    var status by remember { mutableStateOf("Pronto para conectar") }
    var logs by remember { mutableStateOf(listOf<String>()) }
    var busy by remember { mutableStateOf(false) }
    var running by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    var pollJob by remember { mutableStateOf<Job?>(null) }

    fun append(line: String) { logs = (logs + line).takeLast(250) }

    fun startPolling(id: String) {
        pollJob?.cancel()
        pollJob = scope.launch {
            var lastLogId = prefs.getInt("lastLogId_$id", 0)
            while (true) {
                try {
                    val job = apiRequest(apiUrl, apiToken, "/jobs/$id")
                    status = job.optString("status", "unknown")
                    running = status == "queued" || status == "running"
                    val data = apiRequest(apiUrl, apiToken, "/jobs/$id/logs?after=$lastLogId&limit=100")
                    val rows = data.optJSONArray("logs")
                    if (rows != null) for (i in 0 until rows.length()) {
                        val row = rows.getJSONObject(i)
                        lastLogId = maxOf(lastLogId, row.optInt("id"))
                        prefs.edit().putInt("lastLogId_$id", lastLogId).apply()
                        append("[${row.optString("created_at")}] Agent ${row.optInt("agent")}: ${row.optString("message")}")
                    }
                    if (!running) {
                        append("Job terminou com status: $status")
                        break
                    }
                } catch (e: Exception) {
                    status = "Conexão interrompida; tentando novamente: ${e.message ?: "sem detalhes"}"
                    append(status)
                    delay(6000)
                    continue
                }
                delay(4000)
            }
        }
    }

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
                        value = apiUrl,
                        onValueChange = { apiUrl = it.trim() },
                        label = { Text("Backend URL (HTTPS or localhost)") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                }
                item {
                    OutlinedTextField(
                        value = apiToken,
                        onValueChange = { apiToken = it.trim() },
                        label = { Text("API access token") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        visualTransformation = PasswordVisualTransformation()
                    )
                }
                item {
                    OutlinedTextField(
                        value = repo,
                        onValueChange = { repo = it },
                        label = { Text("GitHub repository (owner/repo or new:name)") },
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
                    OutlinedButton(
                        onClick = {
                            scope.launch {
                                busy = true
                                try {
                                    val result = apiRequest(apiUrl, apiToken, "/auth/check")
                                    if (result.optBoolean("authorized")) {
                                        status = "Conectado: token válido"
                                        prefs.edit().putString("apiUrl", apiUrl.trim()).apply()
                                        append("Conexão e token verificados.")
                                    } else {
                                        status = "Token não autorizado"
                                    }
                                } catch (e: Exception) {
                                    status = "Teste falhou: ${e.message ?: "erro desconhecido"}"
                                    append(status)
                                } finally { busy = false }
                            }
                        },
                        enabled = !busy && isAllowedBackendUrl(apiUrl) && apiToken.isNotBlank(),
                        modifier = Modifier.fillMaxWidth()
                    ) { Text(if (busy) "Testing..." else "Test connection") }
                }
                item {
                    Button(
                        onClick = {
                            scope.launch {
                                busy = true
                                try {
                                    val created = apiRequest(
                                        apiUrl, apiToken, "/jobs", "POST",
                                        JSONObject().put("repository", repo.trim())
                                            .put("task", task.trim()).put("agents", agents)
                                    )
                                    jobId = created.getString("id")
                                    prefs.edit().putString("apiUrl", apiUrl.trim())
                                        .putString("repo", repo.trim()).putString("task", task.trim())
                                        .putInt("agents", agents).putString("jobId", jobId).apply()
                                    status = created.optString("status", "queued")
                                    running = true
                                    append("Job criado: $jobId")
                                    startPolling(jobId)
                                } catch (e: Exception) {
                                    status = "Falha ao iniciar: ${e.message}"
                                    append(status)
                                } finally { busy = false }
                            }
                        },
                        enabled = !busy && !running && isAllowedBackendUrl(apiUrl) && apiToken.isNotBlank() &&
                            repo.matches(Regex("^(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+|new:[A-Za-z0-9_.-]+)$")) && task.isNotBlank(),
                        modifier = Modifier.fillMaxWidth()
                    ) { Text(if (busy) "Connecting..." else "Start squad") }
                    if (!running && !busy && jobId.isNotBlank() && isAllowedBackendUrl(apiUrl) && apiToken.isNotBlank()) {
                        OutlinedButton(
                            onClick = {
                                scope.launch {
                                    busy = true
                                    try {
                                        val saved = apiRequest(apiUrl, apiToken, "/jobs/$jobId")
                                        status = saved.optString("status", "unknown")
                                        running = status == "queued" || status == "running"
                                        append("Reconectando ao job $jobId (status: $status)")
                                        if (running) startPolling(jobId)
                                    } catch (e: Exception) {
                                        status = "Falha ao reconectar: ${e.message}"
                                        append(status)
                                    } finally { busy = false }
                                }
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) { Text("Reconnect to last job") }
                    }
                    if (running && jobId.isNotBlank()) {
                        OutlinedButton(
                            onClick = {
                                scope.launch {
                                    busy = true
                                    try {
                                        apiRequest(apiUrl, apiToken, "/jobs/$jobId/stop", "POST", JSONObject())
                                        status = "stopped"
                                        running = false
                                        pollJob?.cancel()
                                        append("Stop solicitado.")
                                    } catch (e: Exception) {
                                        status = "Falha ao parar: ${e.message}"
                                        append(status)
                                    } finally { busy = false }
                                }
                            },
                            enabled = !busy,
                            modifier = Modifier.fillMaxWidth()
                        ) { Text("Stop squad") }
                    }
                    Text("Status: $status", style = MaterialTheme.typography.bodySmall)
                    if (jobId.isNotBlank()) Text("Job: $jobId", style = MaterialTheme.typography.bodySmall)
                    Text("Use HTTPS, or HTTP on localhost only. API keys stay on the server.", style = MaterialTheme.typography.bodySmall)
                }
                item { Text("Activity logs", style = MaterialTheme.typography.titleMedium) }
                items(logs) { line ->
                    Text(line, style = MaterialTheme.typography.bodySmall)
                    HorizontalDivider()
                }
            }
        }
    }
}
