package kr.team4.smishing

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import kr.team4.smishing.Ui.add
import kr.team4.smishing.Ui.addFill

/**
 * 문자 속 링크를 누르면 가장 먼저 열리는 화면.
 * 공식 도메인 → 바로 열기 / 그 외 → '검사 중' 시트 → 서버 판정
 *   안전 → 바로 열기, 주의 → 열면서 안내, 위험 → 경고 화면,
 *   판단 불가·서버 응답 없음 → '확인하지 못했습니다' 화면 (검사 없이 그냥 열지 않는다)
 */
class LinkActivity : Activity() {
    private lateinit var root: FrameLayout
    private val main = Handler(Looper.getMainLooper())
    private var request = 0  // 다시 검사할 때 이전 요청 결과를 무시하기 위한 번호

    companion object {
        private val STEPS = listOf("단축 주소 풀기", "알려진 피싱 목록 확인", "AI 위험 점수 계산")
        private const val STEP_MS = 300L  // 단계 표시 간격(최소 표시 시간 = 3단계 + 0.25초)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        root = FrameLayout(this)
        setContentView(root)
        handle(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handle(intent)
    }

    override fun onDestroy() {
        main.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    private fun handle(intent: Intent?) {
        val url = intent?.data?.toString()
        if (url.isNullOrBlank()) { finish(); return }
        check(url)
    }

    private fun check(url: String) {
        val host = Uri.parse(url).host.orEmpty()
        if (Whitelist(this).isOfficial(host)) {  // 휴대폰 안에서 바로 통과(서버로 보내지 않음)
            History.add(this, defang(url), Verdict.OFFICIAL, null, "공식 기관·기업 주소입니다.", "휴대폰에서 확인")
            toast("공식 기관 주소입니다. 바로 열었어요.")
            openAndFinish(url)
            return
        }
        val my = ++request
        val steps = showChecking(url)
        val started = System.currentTimeMillis()
        for (i in 1..3) main.postDelayed({ if (my == request) steps(i) }, STEP_MS * i)
        Thread {
            val r = Api.check(this, url)
            val wait = (STEP_MS * 3 + 250) - (System.currentTimeMillis() - started)
            main.postDelayed({ if (my == request && !isFinishing) onResult(url, r) }, maxOf(0, wait))
        }.start()
    }

    private fun onResult(url: String, r: CheckResult?) {
        val v = if (r == null) Verdict.UNKNOWN else Verdict.of(r.verdict)
        val reason = when {
            r == null -> "검사 서버가 응답하지 않았습니다."
            r.reasons.isNotEmpty() -> r.reasons.first()
            else -> "AI 위험 점수 ${r.score ?: 0}점 · 특이한 점이 없습니다."
        }
        History.add(this, defang(url), v, r?.score, reason, if (r == null) "서버 응답 없음" else sourceLabel(r.source, v))
        when (v) {
            Verdict.SAFE, Verdict.OFFICIAL -> {
                toast("안전한 링크입니다. ${browserName()}에서 열었어요.")
                openAndFinish(url)
            }
            Verdict.CAUTION -> {
                toast("주의가 필요한 주소입니다. $reason", long = true)
                openAndFinish(url)
            }
            Verdict.DANGER -> showDanger(url, r!!)
            Verdict.UNKNOWN -> showUnknown(url, r)
        }
    }

    private fun openAndFinish(url: String) {
        if (!Browser.open(this, url)) toast("링크를 열 브라우저가 없습니다. Chrome을 설치해 주세요.", long = true)
        finish()
    }

    private fun closeSafely() {
        toast("링크를 열지 않았어요.")
        finish()
    }

    private fun browserName() = Browser.pick(this)?.let { Browser.label(this, it) } ?: "브라우저"

    private fun toast(s: String, long: Boolean = false) =
        Toast.makeText(applicationContext, s, if (long) Toast.LENGTH_LONG else Toast.LENGTH_SHORT).show()

    private fun lightStatusBar(light: Boolean) {
        window.insetsController?.setSystemBarsAppearance(
            if (light) WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS else 0,
            WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS)
    }

    /** 상태 표시줄·내비게이션 막대 높이만큼 위·아래 여백을 더한다 */
    private fun insets(top: View?, bottom: View?) {
        val t0 = top?.paddingTop ?: 0
        val b0 = bottom?.paddingBottom ?: 0
        root.setOnApplyWindowInsetsListener { _, ins ->
            val bars = ins.getInsets(WindowInsets.Type.systemBars())
            top?.setPadding(top.paddingLeft, t0 + bars.top, top.paddingRight, top.paddingBottom)
            bottom?.setPadding(bottom.paddingLeft, bottom.paddingTop, bottom.paddingRight, b0 + bars.bottom)
            ins
        }
        root.requestApplyInsets()
    }

    // ---------- ① 검사 중 (아래에서 올라오는 시트) ----------

    private fun showChecking(url: String): (Int) -> Unit {
        root.removeAllViews()
        root.setBackgroundColor(C.SCRIM)
        lightStatusBar(false)
        val sheet = Ui.col(this, 20).apply { background = Ui.topRounded(context, C.WHITE, 28) }
        Ui.pad(sheet, 24, 28, 24, 32)
        val head = Ui.col(this, 6)
        head.add(Ui.text(this, "링크를 검사하고 있어요", 22, weight = 800))
        head.add(Ui.text(this, defang(url), 14, C.G500, mono = true))
        sheet.add(head)
        val list = Ui.col(this, 14)
        val rows = STEPS.mapIndexed { i, name ->
            val dot = Ui.numDot(this, "${i + 1}", C.G200, C.WHITE, 26)
            val label = Ui.text(this, name, 16, C.G400, 500)
            list.add(Ui.row(this, 12).apply { addView(dot); add(label, ViewGroup.LayoutParams.WRAP_CONTENT) })
            dot to label
        }
        sheet.add(list)
        sheet.add(Ui.text(this, "페이지를 열지 않고 주소만 확인합니다", 13, C.G400))
        root.addView(sheet, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM))
        insets(null, sheet)

        val update = { step: Int ->
            rows.forEachIndexed { i, (dot, label) ->
                val done = step > i
                val active = step == i
                dot.text = if (done) "✓" else "${i + 1}"
                dot.background = Ui.rounded(this, if (done) C.BLUE else if (active) C.G400 else C.G200, 13)
                label.setTextColor(if (done || active) C.INK else C.G400)
                label.typeface = Fonts.get(this, if (active) 700 else 500)
            }
        }
        update(0)
        return update
    }

    // ---------- ② 위험 경고 ----------

    private fun showDanger(url: String, r: CheckResult) {
        val score = r.score ?: 100
        val header = Ui.col(this, 14).apply { setBackgroundColor(C.RED) }
        Ui.pad(header, 24, 28, 24, 26)
        header.addView(Ui.iconTile(this, R.drawable.ic_warning_white, 56, 32, 0x2EFFFFFF, 18))
        header.add(Ui.text(this, "이 링크는 위험합니다.\n여시겠습니까?", 30, C.WHITE, 800, lineSpacing = 1.15f))
        val bar = FrameLayout(this).apply { background = Ui.rounded(context, 0x40FFFFFF, 4) }
        bar.addView(View(this).apply { background = Ui.rounded(context, C.WHITE, 4) },
            FrameLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT))
        val scoreRow = Ui.row(this, 10)
        scoreRow.add(bar, 0, Ui.dp(this, 8), 1f)
        scoreRow.add(Ui.text(this, "위험 점수 $score", 15, C.WHITE, 700), ViewGroup.LayoutParams.WRAP_CONTENT)
        bar.post { bar.getChildAt(0).layoutParams.width = bar.width * score.coerceIn(0, 100) / 100; bar.getChildAt(0).requestLayout() }
        header.add(scoreRow)

        val body = Ui.col(this, 18)
        Ui.pad(body, 24, 22, 24, 22)
        val why = Ui.col(this, 10)
        why.add(Ui.text(this, "위험한 이유", 14, C.G500, 700))
        r.reasons.take(3).forEach { why.add(bullet(it, C.RED)) }
        body.add(why)
        body.add(urlBox(url))
        val afterSteps = Ui.col(this, 8).apply { visibility = View.GONE }
        listOf("1. 모르는 앱이 설치됐다면 바로 삭제", "2. 입력한 비밀번호 변경", "3. 은행에 지급 정지 요청")
            .forEach { afterSteps.add(Ui.text(this, it, 15, C.G700, lineSpacing = 1.2f)) }
        afterSteps.add(Ui.outlineButton(this, "118 상담 전화하기", 44, 15) { dial118() })
        val arrow = Ui.text(this, "+", 16, C.G400)
        val toggle = Ui.row(this).apply {
            add(Ui.text(this@LinkActivity, "이미 눌렀다면 이렇게 하세요", 16, C.INK, 700), 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            add(arrow, ViewGroup.LayoutParams.WRAP_CONTENT)
            Ui.pad(this, 0, 6, 0, 6)
            setOnClickListener {
                val show = afterSteps.visibility != View.VISIBLE
                afterSteps.visibility = if (show) View.VISIBLE else View.GONE
                arrow.text = if (show) "−" else "+"
            }
        }
        body.add(toggle)
        body.add(afterSteps)

        val footer = Ui.col(this, 6)
        Ui.pad(footer, 24, 12, 24, 24)
        footer.add(Ui.primaryButton(this, "닫기 (안전)", bg = C.INK) { closeSafely() })
        footer.add(Ui.linkButton(this, "그래도 열기") { openAnyway(url, danger = true) })

        fullScreen(header, body, footer)
    }

    // ---------- ③ 확인 못 함 ----------

    private fun showUnknown(url: String, r: CheckResult?) {
        val header = Ui.col(this, 14).apply { setBackgroundColor(C.G700) }
        Ui.pad(header, 24, 28, 24, 26)
        header.addView(Ui.text(this, "?", 30, C.WHITE, 800, center = true).apply {
            background = Ui.rounded(context, 0x29FFFFFF, 18)
            layoutParams = LinearLayout.LayoutParams(Ui.dp(context, 56), Ui.dp(context, 56))
        })
        header.add(Ui.text(this, "이 링크를\n확인하지 못했습니다", 30, C.WHITE, 800, lineSpacing = 1.15f))
        header.add(Ui.text(this, "안전한지 알 수 없어 열지 않았어요.", 16, C.G300, lineSpacing = 1.2f))

        val body = Ui.col(this, 18)
        Ui.pad(body, 24, 22, 24, 22)
        val why = Ui.col(this, 10)
        why.add(Ui.text(this, "확인하지 못한 이유", 14, C.G500, 700))
        val reason = if (r == null) "검사 서버가 응답하지 않았습니다. 인터넷 연결을 확인해 주세요."
                     else "단축 주소가 실제로 어디로 가는지 알아내지 못했습니다."
        why.add(bullet(reason, C.G700))
        body.add(why)
        body.add(urlBox(url))
        body.add(Ui.text(this, "보낸 사람을 모르거나 급하게 무언가를 요구하는 문자라면 열지 마세요. 아는 사람이라면 전화로 먼저 확인해 보세요.",
            15, C.G600, lineSpacing = 1.25f))

        val footer = Ui.col(this, 10)
        Ui.pad(footer, 24, 12, 24, 24)
        val grid = Ui.row(this, 10)
        grid.add(Ui.outlineButton(this, "다시 검사") { check(url) }, 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        grid.add(Ui.primaryButton(this, "닫기", size = 17, bg = C.INK) { closeSafely() }, 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        footer.add(grid)
        footer.add(Ui.linkButton(this, "그래도 열기", 40) { openAnyway(url, danger = false) })

        fullScreen(header, body, footer)
    }

    // ---------- 공통 ----------

    private fun fullScreen(header: View, body: View, footer: View) {
        root.removeAllViews()
        root.setBackgroundColor(C.WHITE)
        lightStatusBar(false)
        val page = Ui.col(this)
        page.add(header)
        page.add(ScrollView(this).apply { addView(body) }, ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f)
        page.add(footer)
        root.addFill(page)
        insets(header, footer)
    }

    private fun bullet(s: String, dotColor: Int) = Ui.row(this, 10, center = false).apply {
        val dot = View(context).apply { background = Ui.rounded(context, dotColor, 3) }
        addView(dot, LinearLayout.LayoutParams(Ui.dp(context, 6), Ui.dp(context, 6)).apply { topMargin = Ui.dp(context, 9) })
        add(Ui.text(context, s, 17, C.INK, lineSpacing = 1.2f), 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
    }

    private fun urlBox(url: String) = Ui.col(this, 4).apply {
        background = Ui.rounded(context, C.G100, 12)
        Ui.pad(this, 14, 12, 14, 12)
        add(Ui.text(context, "누른 주소", 12, C.G500, 600))
        add(Ui.text(context, defang(url), 15, C.G700, mono = true).apply { setTextIsSelectable(false) })
    }

    private fun openAnyway(url: String, danger: Boolean) {
        toast(if (danger) "위험한 링크를 열었습니다. 아무것도 입력하거나 설치하지 마세요."
              else "확인하지 못한 링크입니다. 개인정보 입력에 주의하세요.", long = true)
        openAndFinish(url)
    }

    private fun dial118() {
        try { startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:118"))) } catch (e: Exception) { }
    }
}
