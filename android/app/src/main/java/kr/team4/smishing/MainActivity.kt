package kr.team4.smishing

import android.app.Activity
import android.app.AlertDialog
import android.app.role.RoleManager
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Toast
import kr.team4.smishing.Ui.add
import kr.team4.smishing.Ui.addFill

/** 처음 설정 → 홈 · 검사 기록 · 도움말(하단 탭) */
class MainActivity : Activity() {
    private enum class Screen { ONBOARD, HOME, HISTORY, HELP }

    private lateinit var root: FrameLayout
    private var screen = Screen.HOME
    private var filter = "all"

    companion object { private const val REQ_ROLE = 1 }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        root = FrameLayout(this).apply { setBackgroundColor(C.BG) }
        setContentView(root)
        window.insetsController?.setSystemBarsAppearance(
            WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
            WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS)
        screen = if (!Prefs.onboarded(this) && !isProtected(this)) Screen.ONBOARD else Screen.HOME
    }

    override fun onResume() {
        super.onResume()
        Thread { Endpoint.refresh(applicationContext) }.start()  // 시연 서버 주소를 미리 받아 둔다
        render()  // 기록·보호 상태가 바뀌었을 수 있으니 매번 다시 그림
    }

    @Deprecated("Activity 기본 API 사용")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION") super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQ_ROLE && isProtected(this)) {
            Prefs.setOnboarded(this)
            screen = Screen.HOME
            Toast.makeText(this, "보호를 켰어요. 링크는 ${browserName()}에서 엽니다.", Toast.LENGTH_SHORT).show()
        }
        render()
    }

    private fun go(s: Screen) { screen = s; render() }

    private fun render() {
        root.removeAllViews()
        if (screen == Screen.ONBOARD) { onboard(); return }
        val page = Ui.col(this)
        val content = when (screen) {
            Screen.HISTORY -> history()
            Screen.HELP -> help()
            else -> home()
        }
        page.add(ScrollView(this).apply { addView(content); isFillViewport = true }, ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f)
        val nav = navBar()
        page.add(nav)
        root.addFill(page)
        insets(page, nav)
    }

    /** 상태 표시줄·내비게이션 막대만큼 여백 */
    private fun insets(top: View, bottom: View?) {
        val t0 = top.paddingTop
        val b0 = bottom?.paddingBottom ?: 0
        root.setOnApplyWindowInsetsListener { _, ins ->
            val bars = ins.getInsets(WindowInsets.Type.systemBars())
            top.setPadding(top.paddingLeft, t0 + bars.top, top.paddingRight, top.paddingBottom)
            bottom?.setPadding(bottom.paddingLeft, bottom.paddingTop, bottom.paddingRight, b0 + bars.bottom)
            ins
        }
        root.requestApplyInsets()
    }

    private fun browserName() = Browser.pick(this)?.let { Browser.label(this, it) } ?: "브라우저"

    private fun requestRole() {
        val rm = getSystemService(RoleManager::class.java)
        if (rm != null && rm.isRoleAvailable(RoleManager.ROLE_BROWSER) && !rm.isRoleHeld(RoleManager.ROLE_BROWSER)) {
            @Suppress("DEPRECATION")
            startActivityForResult(rm.createRequestRoleIntent(RoleManager.ROLE_BROWSER), REQ_ROLE)
        } else {
            // 이미 켜져 있으면(끄려는 경우) 기본 앱 설정 화면으로
            startActivity(Intent(Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS))
        }
    }

    // ---------- ① 처음 설정 ----------

    private fun onboard() {
        val page = Ui.col(this).apply { setBackgroundColor(C.WHITE) }
        Ui.pad(page, 24, 24, 24, 28)
        val brand = Ui.row(this, 8)
        brand.addView(Ui.icon(this, R.drawable.ic_shield_blue, 22))
        brand.add(Ui.text(this, "KoK", 15, C.BLUE, 700), ViewGroup.LayoutParams.WRAP_CONTENT)
        page.add(brand)

        val mid = Ui.col(this, 28).apply { gravity = Gravity.CENTER_VERTICAL }
        mid.addView(Ui.iconTile(this, R.drawable.ic_shield_check_blue, 112, 60, C.BLUE_SOFT, 32))
        val copy = Ui.col(this, 14)
        copy.add(Ui.text(this, "문자 속 링크,\n누르기 전에\n먼저 검사해 드려요", 30, weight = 800, lineSpacing = 1.15f))
        copy.add(Ui.text(this, "한 번만 켜 두면 평소처럼 누르기만 하면 됩니다. 위험할 때만 알려 드려요.", 17, C.G600, lineSpacing = 1.25f))
        mid.add(copy)
        val steps = Ui.col(this, 12)
        listOf("은행·택배·공공기관 공식 주소는 바로 열립니다", "처음 보는 주소는 AI가 위험 점수를 매깁니다", "위험하면 열기 전에 한 번 더 묻습니다")
            .forEachIndexed { i, s -> steps.add(numbered(i + 1, s, C.BLUE_SOFT, C.BLUE)) }
        mid.add(steps)
        page.add(mid, ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f)

        val bottom = Ui.col(this, 14)
        bottom.add(Ui.text(this, "누른 링크 주소는 검사를 위해 서버로 보내지며, 저장하지 않습니다. 링크는 검사 후 ${browserName()}에서 엽니다.",
            13, C.G500, lineSpacing = 1.25f))
        bottom.add(Ui.primaryButton(this, "보호 켜기") { requestRole() })
        page.add(bottom)
        root.addFill(ScrollView(this).apply { isFillViewport = true; addView(page); setBackgroundColor(C.WHITE) })
        insets(page, page)
    }

    private fun numbered(n: Int, s: String, bg: Int, fg: Int) = Ui.row(this, 12, center = false).apply {
        addView(Ui.numDot(context, "$n", bg, fg))
        add(Ui.text(context, s, 15, C.G700, lineSpacing = 1.2f), 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
    }

    // ---------- 홈 ----------

    private fun home(): View {
        val c = Ui.col(this, 16)
        Ui.pad(c, 20, 16, 20, 24)
        c.add(Ui.text(this, "KoK", 20, weight = 800).apply { minHeight = Ui.dp(context, 44); gravity = Gravity.CENTER_VERTICAL })

        if (isProtected(this)) {
            val card = Ui.col(this, 18).apply { background = Ui.rounded(context, C.BLUE, 24) }
            Ui.pad(card, 24)
            val top = Ui.row(this, 14)
            top.addView(Ui.iconTile(this, R.drawable.ic_shield_check_white, 56, 32, 0x29FFFFFF, 18))
            val t = Ui.col(this, 2)
            t.add(Ui.text(this, "보호 중입니다", 24, C.WHITE, 800))
            t.add(Ui.text(this, "문자 속 링크를 누르면 먼저 검사해요", 15, C.BLUE_TINT))
            top.add(t, 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            card.add(top)
            val stats = Ui.row(this, 10)
            stats.add(stat("검사한 링크", History.total(this)), 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            stats.add(stat("막은 위험 링크", History.blocked(this)), 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            card.add(stats)
            c.add(card)
        } else {
            val card = Ui.col(this, 16).apply { background = Ui.rounded(context, C.WHITE, 24, C.RED_LINE, 2) }
            Ui.pad(card, 24)
            val t = Ui.col(this, 6)
            t.add(Ui.text(this, "보호가 꺼져 있습니다", 24, C.RED_TEXT, 800))
            t.add(Ui.text(this, "지금은 링크가 검사 없이 바로 열립니다.", 15, C.G600, lineSpacing = 1.2f))
            card.add(t)
            card.add(Ui.primaryButton(this, "보호 다시 켜기", 54, 17, radius = 14) { requestRole() })
            c.add(card)
        }

        // 시연용 문자 화면으로
        val demo = Ui.row(this, 14).apply {
            background = Ui.ripple(Ui.rounded(context, C.WHITE, 18, C.G200))
            Ui.pad(this, 18, 16, 18, 16)
            setOnClickListener { startActivity(Intent(context, DemoSmsActivity::class.java)) }
        }
        demo.addView(Ui.iconTile(this, R.drawable.ic_sms, 44, 24, C.G100, 14))
        val dt = Ui.col(this, 2)
        dt.add(Ui.text(this, "문자 앱에서 시험해 보기", 17, C.INK, 700))
        dt.add(Ui.text(this, "시연용 문자 속 링크를 눌러 보세요", 14, C.G500))
        demo.add(dt, 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        demo.add(Ui.text(this, "›", 22, C.G400), ViewGroup.LayoutParams.WRAP_CONTENT)
        c.add(demo)

        // 최근 검사
        val recentHead = Ui.row(this)
        recentHead.add(Ui.text(this, "최근 검사", 17, weight = 700), 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        recentHead.add(Ui.text(this, "전체 보기", 14, C.BLUE, 600).apply {
            Ui.pad(this, 0, 6, 0, 6); setOnClickListener { go(Screen.HISTORY) }
        }, ViewGroup.LayoutParams.WRAP_CONTENT)
        val recentBox = Ui.col(this, 10)
        recentBox.add(recentHead)
        val recent = History.all(this).take(3)
        val list = Ui.card(this, 18)
        if (recent.isEmpty()) {
            list.add(Ui.pad(Ui.text(this, "아직 검사한 링크가 없습니다", 15, C.G400, center = true), 24))
        }
        recent.forEachIndexed { i, r ->
            if (i > 0) list.addView(Ui.divider(this))
            val row = Ui.row(this, 12)
            Ui.pad(row, 16, 14, 16, 14)
            row.addView(Ui.badge(this, r.verdict))
            val t = Ui.col(this, 2)
            t.add(Ui.ellipsize(Ui.text(this, r.url, 15, C.INK, mono = true)))
            t.add(Ui.text(this, "${History.when_(r.time)} · ${r.source}", 13, C.G500))
            row.add(t, 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            list.add(row)
        }
        recentBox.add(list)
        c.add(recentBox)
        return c
    }

    private fun stat(label: String, n: Int) = Ui.col(this, 2).apply {
        background = Ui.rounded(context, 0x1FFFFFFF, 14)
        Ui.pad(this, 14, 12, 14, 12)
        add(Ui.text(context, label, 13, C.BLUE_TINT))
        add(Ui.text(context, "${n}건", 24, C.WHITE, 800))
    }

    // ---------- ④ 검사 기록 ----------

    private fun history(): View {
        val c = Ui.col(this, 14)
        Ui.pad(c, 20, 22, 20, 24)
        val head = Ui.col(this, 4)
        head.add(Ui.text(this, "검사 기록", 24, weight = 800))
        head.add(Ui.text(this, "최근 50개까지 이 휴대폰에만 저장됩니다", 14, C.G500))
        c.add(head)

        val chips = Ui.row(this, 8)
        listOf("all" to "전체", "danger" to "위험", "caution" to "주의", "safe" to "안전").forEach { (k, name) ->
            val on = filter == k
            chips.add(Ui.text(this, name, 15, if (on) C.WHITE else C.G700, 600, center = true).apply {
                background = Ui.rounded(context, if (on) C.INK else C.WHITE, 19, if (on) C.INK else C.G300)
                minHeight = Ui.dp(context, 38)
                setPadding(Ui.dp(context, 16), 0, Ui.dp(context, 16), 0)
                setOnClickListener { filter = k; render() }
            }, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
        c.add(chips)

        val keep = when (filter) {
            "danger" -> setOf(Verdict.DANGER)
            "caution" -> setOf(Verdict.CAUTION, Verdict.UNKNOWN)
            "safe" -> setOf(Verdict.SAFE, Verdict.OFFICIAL)
            else -> Verdict.entries.toSet()
        }
        val items = History.all(this).filter { it.verdict in keep }
        val list = Ui.col(this, 10)
        items.forEach { r ->
            val card = Ui.col(this, 8).apply { background = Ui.rounded(context, C.WHITE, 16, C.G200) }
            Ui.pad(card, 16, 14, 16, 14)
            val top = Ui.row(this, 8)
            top.addView(Ui.badge(this, r.verdict).apply { setPadding(Ui.dp(context, 10), 0, Ui.dp(context, 10), 0) })
            top.add(Ui.spacer(this), 0, 1, 1f)
            top.add(Ui.text(this, History.when_(r.time), 13, C.G400), ViewGroup.LayoutParams.WRAP_CONTENT)
            card.add(top)
            card.add(Ui.text(this, r.url, 15, C.INK, mono = true))
            if (r.reason.isNotBlank()) card.add(Ui.text(this, r.reason, 14, C.G600, lineSpacing = 1.2f))
            list.add(card)
        }
        if (items.isEmpty()) list.add(Ui.pad(Ui.text(this, "해당하는 기록이 없습니다", 15, C.G400, center = true), 0, 40, 0, 40))
        c.add(list)
        return c
    }

    // ---------- 도움말 ----------

    private fun help(): View {
        val c = Ui.col(this, 14)
        Ui.pad(c, 20, 22, 20, 24)
        c.add(Ui.text(this, "도움말", 24, weight = 800))

        val call = Ui.row(this, 14).apply {
            background = Ui.ripple(Ui.rounded(context, C.INK, 18), 0x33FFFFFF)
            Ui.pad(this, 18)
            setOnClickListener { startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:118"))) }
        }
        call.addView(Ui.text(this, "118", 17, C.WHITE, 800, center = true).apply {
            background = Ui.rounded(context, 0x1FFFFFFF, 16)
            layoutParams = LinearLayout.LayoutParams(Ui.dp(context, 48), Ui.dp(context, 48))
        })
        val ct = Ui.col(this, 2)
        ct.add(Ui.text(this, "118 상담 전화", 18, C.WHITE, 700))
        ct.add(Ui.text(this, "한국인터넷진흥원 · 24시간 무료", 14, 0xFFC7CEDB.toInt()))
        call.add(ct, 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        c.add(call)

        val after = Ui.card(this, 18, 14)
        Ui.pad(after, 18)
        after.add(Ui.text(this, "이미 링크를 눌렀다면", 17, weight = 700))
        listOf("모르는 앱이 설치됐다면 바로 삭제하세요", "입력한 비밀번호는 바로 바꾸세요", "금융 정보를 입력했다면 은행에 지급 정지를 요청하세요")
            .forEachIndexed { i, s -> after.add(numbered(i + 1, s, C.RED_SOFT, C.RED_TEXT)) }
        c.add(after)

        val settings = Ui.card(this, 18)
        // 링크 보호 스위치(실제 상태 = 기본 브라우저 역할 여부)
        val on = isProtected(this)
        val protectRow = Ui.row(this, 12).apply { Ui.pad(this, 18, 16, 18, 16); setOnClickListener { requestRole() } }
        val pt = Ui.col(this, 2)
        pt.add(Ui.text(this, "링크 보호", 16, weight = 700))
        pt.add(Ui.text(this, "기본 브라우저 역할로 링크를 먼저 받습니다", 13, C.G500))
        protectRow.add(pt, 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        protectRow.addView(switch(on))
        settings.add(protectRow)
        settings.addView(Ui.divider(this))
        // 링크를 열 브라우저
        val browserRow = Ui.row(this, 12).apply { Ui.pad(this, 18, 16, 18, 16); setOnClickListener { chooseBrowser() } }
        val bt = Ui.col(this, 2)
        bt.add(Ui.text(this, "링크를 열 브라우저", 16, weight = 700))
        bt.add(Ui.text(this, browserName(), 13, C.G500))
        browserRow.add(bt, 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        browserRow.add(Ui.text(this, "›", 22, C.G400), ViewGroup.LayoutParams.WRAP_CONTENT)
        settings.add(browserRow)
        settings.addView(Ui.divider(this))
        val privacy = Ui.col(this, 6)
        Ui.pad(privacy, 18, 16, 18, 16)
        privacy.add(Ui.text(this, "개인정보", 16, weight = 700))
        privacy.add(Ui.text(this, "공식 기관·기업 주소는 휴대폰 안에서 확인하고 서버로 보내지 않습니다. 서버는 링크 페이지를 열지 않고 주소만 검사하며, 검사한 주소를 저장하지 않습니다.",
            14, C.G600, lineSpacing = 1.25f))
        settings.add(privacy)
        settings.add(Ui.pad(Ui.text(this, "카카오톡처럼 자체 브라우저로 여는 앱의 링크는 검사할 수 없습니다.", 13, C.G400, lineSpacing = 1.2f), 18, 0, 18, 16))
        c.add(settings)
        return c
    }

    private fun switch(on: Boolean) = FrameLayout(this).apply {
        background = Ui.rounded(context, if (on) C.BLUE else C.G300, 16)
        Ui.pad(this, 3)
        addView(View(context).apply { background = Ui.rounded(context, C.WHITE, 13); elevation = Ui.dp(context, 1).toFloat() },
            FrameLayout.LayoutParams(Ui.dp(context, 26), Ui.dp(context, 26), if (on) Gravity.END else Gravity.START))
        layoutParams = LinearLayout.LayoutParams(Ui.dp(context, 56), Ui.dp(context, 32))
    }

    private fun chooseBrowser() {
        val list = Browser.candidates(this)
        if (list.isEmpty()) return
        AlertDialog.Builder(this).setTitle("링크를 열 브라우저")
            .setItems(list.map { Browser.label(this, it) }.toTypedArray()) { _, i -> Prefs.setBrowser(this, list[i]); render() }
            .show()
    }

    // ---------- 하단 탭 ----------

    private fun navBar() = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        setBackgroundColor(C.WHITE)
        listOf(Screen.HOME to "홈", Screen.HISTORY to "검사 기록", Screen.HELP to "도움말").forEach { (s, name) ->
            val active = screen == s
            val item = Ui.col(context, 4).apply {
                gravity = Gravity.CENTER
                minimumHeight = Ui.dp(context, 72)
                setOnClickListener { go(s) }
            }
            item.addView(View(context).apply { background = Ui.rounded(context, if (active) C.BLUE else 0, 2) },
                LinearLayout.LayoutParams(Ui.dp(context, 28), Ui.dp(context, 4)))
            item.addView(Ui.text(context, name, 15, if (active) C.BLUE else C.G500, 700, center = true))
            addView(item, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
        // 위쪽 1dp 경계선
        foreground = android.graphics.drawable.LayerDrawable(arrayOf(android.graphics.drawable.ColorDrawable(C.G200))).apply {
            setLayerGravity(0, Gravity.TOP or Gravity.FILL_HORIZONTAL)
            setLayerHeight(0, Ui.dp(context, 1))
        }
    }
}
