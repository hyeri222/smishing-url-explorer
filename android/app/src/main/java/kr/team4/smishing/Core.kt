package kr.team4.smishing

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/** 서버 판정 결과 */
data class CheckResult(
    val verdict: String,          // safe | caution | danger | unknown
    val score: Int?,
    val finalUrl: String,
    val chain: List<String>,
    val reasons: List<String>,    // 화면에 보일 이유 문장
    val source: String,
)

/** 검사 서버(FastAPI) 호출. 실패하면 null → 화면에서 '확인하지 못함'으로 처리 */
object Api {
    private const val TIMEOUT_MS = 4000  // 서버는 단축 주소 풀기(최대 1.5초) + 주소 조회(최대 0.9초) + AI 계산을 한다

    fun check(ctx: Context, url: String): CheckResult? {
        val base = Endpoint.base(ctx)
        post(base, url)?.let { return it }
        // 시연 서버(무료 터널)는 켤 때마다 주소가 바뀐다 → 새 주소를 받아 한 번 더 시도
        val fresh = Endpoint.refresh(ctx)
        return if (fresh != null && fresh != base) post(fresh, url) else null
    }

    private fun post(base: String, url: String): CheckResult? = try {
        val conn = URL("$base/api/check").openConnection() as HttpURLConnection
        conn.connectTimeout = TIMEOUT_MS
        conn.readTimeout = TIMEOUT_MS
        conn.requestMethod = "POST"
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
        conn.outputStream.use { it.write(JSONObject().put("url", url).toString().toByteArray()) }
        if (conn.responseCode != 200) null
        else parse(JSONObject(conn.inputStream.bufferedReader().readText()))
    } catch (e: Exception) {
        android.util.Log.w("SmishingApi", "검사 서버 호출 실패($base): ${e.javaClass.simpleName}: ${e.message}")
        null
    }

    fun parse(j: JSONObject): CheckResult {
        val reasons = j.optJSONArray("reasons") ?: JSONArray()
        val chain = j.optJSONArray("chain") ?: JSONArray()
        return CheckResult(
            verdict = j.optString("verdict", "unknown"),
            score = if (j.isNull("score")) null else j.optInt("score"),
            finalUrl = j.optString("final_url"),
            chain = (0 until chain.length()).map { chain.getString(it) },
            reasons = (0 until reasons.length()).map { reasons.getJSONObject(it).optString("text") },
            source = j.optString("source"),
        )
    }
}

/**
 * 검사 서버 주소. ENDPOINT_URL(허깅페이스에 둔 endpoint.txt)이 있으면 거기 적힌 주소를 쓰고,
 * 받은 주소는 기기에 저장해 두었다가 다음에 바로 쓴다. 없으면 빌드할 때 넣은 API_BASE.
 */
object Endpoint {
    private fun sp(ctx: Context) = ctx.getSharedPreferences("app", Context.MODE_PRIVATE)

    fun base(ctx: Context): String {
        if (BuildConfig.ENDPOINT_URL.isEmpty()) return BuildConfig.API_BASE
        return sp(ctx).getString("endpoint", null) ?: refresh(ctx) ?: BuildConfig.API_BASE
    }

    /** endpoint.txt를 다시 읽는다(네트워크 사용, 메인 스레드에서 부르지 말 것) */
    fun refresh(ctx: Context): String? {
        if (BuildConfig.ENDPOINT_URL.isEmpty()) return null
        return try {
            val conn = URL(BuildConfig.ENDPOINT_URL).openConnection() as HttpURLConnection
            conn.connectTimeout = 3000
            conn.readTimeout = 3000
            val u = conn.inputStream.bufferedReader().readText().trim().trimEnd('/')
            if (!u.matches(Regex("https://[a-z0-9.-]+"))) null  // https 주소만 받는다
            else u.also { sp(ctx).edit().putString("endpoint", it).apply() }
        } catch (e: Exception) {
            null
        }
    }
}

/** 공식 도메인 목록(앱 안에 내장). 여기 있으면 서버에 묻지 않고 바로 연다 */
class Whitelist(context: Context) {
    private val entries: List<String> = context.assets.open("whitelist.txt").bufferedReader().readLines()
        .map { it.trim().lowercase() }.filter { it.isNotEmpty() && !it.startsWith("#") }

    fun isOfficial(host: String): Boolean {
        val h = host.lowercase().trimEnd('.')
        return entries.any { e ->
            if (e.startsWith(".")) h.endsWith(e) else h == e || h.endsWith(".$e")
        }
    }
}

/** 실제로 링크를 열어 줄 브라우저(크롬, 삼성 인터넷 등) */
object Browser {
    private val PREFERRED = listOf("com.android.chrome", "com.sec.android.app.sbrowser", "org.mozilla.firefox",
        "com.microsoft.emmx", "com.naver.whale")

    fun candidates(ctx: Context): List<String> {
        val probe = Intent(Intent.ACTION_VIEW, Uri.parse("https://example.com")).addCategory(Intent.CATEGORY_BROWSABLE)
        return ctx.packageManager.queryIntentActivities(probe, PackageManager.MATCH_ALL)
            .map { it.activityInfo.packageName }
            .filter { it != ctx.packageName }
            .distinct()
    }

    fun pick(ctx: Context): String? {
        val saved = Prefs.browser(ctx)
        val list = candidates(ctx)
        if (saved != null && saved in list) return saved
        return PREFERRED.firstOrNull { it in list } ?: list.firstOrNull()
    }

    /** 우리 앱을 거치지 않고 진짜 브라우저로 연다(다시 우리 앱으로 돌아오는 무한 반복 방지) */
    fun open(ctx: Context, url: String): Boolean {
        val pkg = pick(ctx) ?: return false
        val i = Intent(Intent.ACTION_VIEW, Uri.parse(url)).setPackage(pkg)
            .addCategory(Intent.CATEGORY_BROWSABLE).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        return try {
            ctx.startActivity(i); true
        } catch (e: Exception) {
            false
        }
    }

    fun label(ctx: Context, pkg: String): String = try {
        ctx.packageManager.getApplicationLabel(ctx.packageManager.getApplicationInfo(pkg, 0)).toString()
    } catch (e: Exception) { pkg }
}

object Prefs {
    private fun sp(ctx: Context) = ctx.getSharedPreferences("app", Context.MODE_PRIVATE)
    fun browser(ctx: Context): String? = sp(ctx).getString("browser", null)
    fun setBrowser(ctx: Context, pkg: String) = sp(ctx).edit().putString("browser", pkg).apply()
    fun onboarded(ctx: Context) = sp(ctx).getBoolean("onboarded", false)
    fun setOnboarded(ctx: Context) = sp(ctx).edit().putBoolean("onboarded", true).apply()
}

/** 보호 켜짐 = 우리 앱이 기본 브라우저 역할을 갖고 있음 */
fun isProtected(ctx: Context): Boolean =
    ctx.getSystemService(android.app.role.RoleManager::class.java)
        ?.isRoleHeld(android.app.role.RoleManager.ROLE_BROWSER) == true

/** 기록 한 줄 */
data class Record(val url: String, val verdict: Verdict, val score: Int?, val reason: String, val source: String, val time: Long)

/** 검사 기록: 기기 안에만 최근 50개 저장(서버에는 저장하지 않음). 홈 화면 숫자는 따로 누적 */
object History {
    private const val MAX = 50
    private fun sp(ctx: Context) = ctx.getSharedPreferences("history", Context.MODE_PRIVATE)

    fun add(ctx: Context, url: String, verdict: Verdict, score: Int?, reason: String?, source: String) {
        val arr = JSONArray(sp(ctx).getString("items", "[]"))
        val item = JSONObject().put("url", url).put("verdict", verdict.key).put("score", score ?: JSONObject.NULL)
            .put("reason", reason ?: "").put("source", source).put("time", System.currentTimeMillis())
        val out = JSONArray().put(item)
        for (i in 0 until minOf(arr.length(), MAX - 1)) out.put(arr.get(i))
        sp(ctx).edit().putString("items", out.toString())
            .putInt("total", total(ctx) + 1)
            .putInt("blocked", blocked(ctx) + if (verdict == Verdict.DANGER) 1 else 0)
            .apply()
    }

    fun all(ctx: Context): List<Record> {
        val arr = JSONArray(sp(ctx).getString("items", "[]"))
        return (0 until arr.length()).map { arr.getJSONObject(it) }.map {
            Record(it.optString("url"), Verdict.of(it.optString("verdict")),
                if (it.isNull("score")) null else it.optInt("score"),
                it.optString("reason"), it.optString("source"), it.optLong("time"))
        }
    }

    fun total(ctx: Context) = sp(ctx).getInt("total", 0)
    fun blocked(ctx: Context) = sp(ctx).getInt("blocked", 0)

    /** '오늘 오후 3:22', '어제 오후 7:31', '11월 2일' */
    fun when_(time: Long): String {
        val now = java.util.Calendar.getInstance()
        val t = java.util.Calendar.getInstance().apply { timeInMillis = time }
        val days = ((startOfDay(now) - startOfDay(t)) / 86_400_000L).toInt()
        val h = t.get(java.util.Calendar.HOUR_OF_DAY)
        val hm = "${if (h < 12) "오전" else "오후"} ${(h + 11) % 12 + 1}:%02d".format(t.get(java.util.Calendar.MINUTE))
        return when (days) {
            0 -> "오늘 $hm"
            1 -> "어제 $hm"
            else -> "${t.get(java.util.Calendar.MONTH) + 1}월 ${t.get(java.util.Calendar.DAY_OF_MONTH)}일"
        }
    }

    private fun startOfDay(c: java.util.Calendar) = (c.clone() as java.util.Calendar).apply {
        set(java.util.Calendar.HOUR_OF_DAY, 0); set(java.util.Calendar.MINUTE, 0)
        set(java.util.Calendar.SECOND, 0); set(java.util.Calendar.MILLISECOND, 0)
    }.timeInMillis
}

/** 서버 응답의 source → 기록에 보일 출처 */
fun sourceLabel(source: String, verdict: Verdict): String = when {
    source == "blacklist" -> "피싱 목록"
    source == "whitelist" -> "공식 주소"
    source == "trace_not_found" -> "삭제된 단축 주소"
    source == "shortener_blocked" -> "단축 서비스 차단"
    source.startsWith("trace") -> "목적지 확인 실패"
    source == "canine" -> "AI 판단"
    source == "canine+rules" -> "AI + 규칙"
    source == "rules_fallback" -> "임시 규칙(모델 없음)"
    else -> verdict.source
}

/** 화면에 주소를 보여 줄 때 실수로 눌리지 않게: https → hxxps, . → [.] */
fun defang(url: String): String {
    val scheme = if (url.startsWith("https")) "hxxps" else "hxxp"
    return "$scheme://" + url.substringAfter("://").replace(".", "[.]")
}
