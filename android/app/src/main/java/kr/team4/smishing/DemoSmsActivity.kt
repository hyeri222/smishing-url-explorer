package kr.team4.smishing

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import kr.team4.smishing.Ui.add
import kr.team4.smishing.Ui.addFill

/**
 * 학술제 시연용 '가짜 문자 앱'. 받은 문자 목록 → 보낸 사람을 골라 들어가 → 링크를 누르면
 * 실제 검사 흐름(LinkActivity → 서버)을 그대로 탄다.
 * 주소는 모두 시연용이다: 택배 주소는 server/data/demo_blacklist.txt의 가짜 도메인,
 * 쇼핑몰 주소는 등록되지 않은 도메인이라 열려도 아무 페이지도 뜨지 않는다.
 */
class DemoSmsActivity : Activity() {

    private data class Sms(val from: String, val avatar: String, val avatarBg: Int, val text: String,
                           val url: String, val time: String)

    private val messages = listOf(
        Sms("02-3150-88xx", "0", 0xFFFEE4E2.toInt(), "[교통민원24] 미납 과태료 고지서가 발송되었습니다. 조회:",
            "http://bit.ly/3xQw9Kd", "오전 8:03"),
        Sms("#Web발신 070-4512-38xx", "#", 0xFFE4E7EC.toInt(), "[CJ대한통운] 고객님 택배가 주소지 불일치로 보관 중입니다. 주소 확인:",
            "http://cj-1ogistics-demo.top/addr", "오전 9:12"),
        Sms("010-2931-55xx", "0", 0xFFFDE2C8.toInt(), "저희 두 사람 결혼합니다. 모바일 청첩장 보기",
            "https://t.ly/Wd9kQ2", "오전 10:40"),
        Sms("국민건강보험", "국", 0xFFD1E9FF.toInt(), "[국민건강보험] 올해 건강검진 대상자입니다. 검진기관 찾기",
            "https://www.nhis.or.kr", "오후 1:05"),
        Sms("하루마켓", "하", 0xFFD3F8DF.toInt(), "[하루마켓] 주문하신 상품이 출발했습니다. 배송 조회",
            "https://haru-deliv.kr/t/88231", "오후 3:22"),
        Sms("김민지", "김", 0xFFEBE9FE.toInt(), "어제 말한 옷 여기서 샀어",
            "https://www.musinsa.com/products/123456", "오후 5:48"),
    ).reversed()  // 최근 문자가 위로

    private val read = HashSet<Int>()
    private var open: Int? = null  // 열어 본 대화(없으면 목록)
    private lateinit var root: FrameLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.insetsController?.setSystemBarsAppearance(
            WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS, WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS)
        root = FrameLayout(this).apply { setBackgroundColor(C.WHITE) }
        setContentView(root)
        root.setOnApplyWindowInsetsListener { v, ins ->
            val b = ins.getInsets(WindowInsets.Type.systemBars())
            v.setPadding(0, b.top, 0, b.bottom)
            ins
        }
        render()
    }

    @Deprecated("Activity 기본 API 사용")
    override fun onBackPressed() {
        if (open != null) { open = null; render() } else @Suppress("DEPRECATION") super.onBackPressed()
    }

    private fun render() {
        root.removeAllViews()
        root.addFill(open?.let { thread(it) } ?: inbox())
    }

    // ---------- 받은 문자 목록 ----------

    private fun inbox(): View {
        val page = Ui.col(this)
        val bar = Ui.row(this, 8).apply { Ui.pad(this, 8, 0, 20, 0); minimumHeight = Ui.dp(context, 64) }
        bar.add(Ui.text(this, "←", 22, C.G700, center = true).apply {
            minWidth = Ui.dp(context, 48); minHeight = Ui.dp(context, 48); setOnClickListener { finish() }
        }, ViewGroup.LayoutParams.WRAP_CONTENT)
        val title = Ui.col(this)
        title.add(Ui.text(this, "메시지", 22, weight = 700))
        title.add(Ui.text(this, "시연용 가짜 문자 · 눌러서 열어 보세요", 12, C.G400))
        bar.add(title, 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        page.add(bar)

        val list = Ui.col(this)
        messages.forEachIndexed { i, m ->
            val unread = i !in read
            val row = Ui.row(this, 14).apply {
                background = Ui.ripple(android.graphics.drawable.ColorDrawable(C.WHITE))
                Ui.pad(this, 20, 14, 20, 14)
                setOnClickListener { read += i; open = i; render() }
            }
            row.addView(avatar(m, 48))
            val mid = Ui.col(this, 4)
            val top = Ui.row(this, 8)
            top.add(Ui.ellipsize(Ui.text(this, m.from, 16, C.INK, if (unread) 700 else 500)), 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            top.add(Ui.text(this, m.time, 12, if (unread) C.BLUE else C.G400, if (unread) 700 else 400), ViewGroup.LayoutParams.WRAP_CONTENT)
            mid.add(top)
            val bottom = Ui.row(this, 8)
            bottom.add(Ui.ellipsize(Ui.text(this, "${m.text} ${m.url}", 14, if (unread) C.G700 else C.G500, if (unread) 600 else 400)),
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            if (unread) bottom.addView(View(this).apply { background = Ui.rounded(context, C.BLUE, 5) },
                LinearLayout.LayoutParams(Ui.dp(this, 10), Ui.dp(this, 10)))
            mid.add(bottom)
            row.add(mid, 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            list.add(row)
        }
        page.add(ScrollView(this).apply { addView(list) }, ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f)
        return page
    }

    private fun avatar(m: Sms, sizeDp: Int) = Ui.text(this, m.avatar, sizeDp * 0.36f, C.G700, 700, center = true).apply {
        background = Ui.rounded(context, m.avatarBg, sizeDp / 2)
        layoutParams = LinearLayout.LayoutParams(Ui.dp(context, sizeDp), Ui.dp(context, sizeDp))
    }

    // ---------- 대화 화면 ----------

    private fun thread(i: Int): View {
        val m = messages[i]
        val page = Ui.col(this)
        val bar = Ui.row(this, 8).apply { Ui.pad(this, 8, 0, 8, 0); minimumHeight = Ui.dp(context, 64) }
        bar.add(Ui.text(this, "←", 22, C.G700, center = true).apply {
            minWidth = Ui.dp(context, 48); minHeight = Ui.dp(context, 48); setOnClickListener { open = null; render() }
        }, ViewGroup.LayoutParams.WRAP_CONTENT)
        bar.addView(avatar(m, 36))
        val title = Ui.col(this)
        title.add(Ui.ellipsize(Ui.text(this, m.from, 17, weight = 600)))
        title.add(Ui.text(this, "시연용 가짜 문자", 12, C.G400))
        bar.add(title, 0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        page.add(bar)
        page.addView(Ui.divider(this))

        val list = Ui.col(this, 6).apply { setBackgroundColor(0xFFF7F8FA.toInt()) }
        Ui.pad(list, 14, 16, 14, 16)
        list.add(Ui.text(this, "오늘", 12, C.G400, center = true).apply { Ui.pad(this, 0, 0, 0, 10) })
        val bubble = Ui.col(this, 4).apply {
            background = android.graphics.drawable.GradientDrawable().apply {
                setColor(C.WHITE); setStroke(Ui.dp(context, 1), 0xFFEAECF0.toInt())
                val r = Ui.dp(context, 18).toFloat(); val s = Ui.dp(context, 4).toFloat()
                cornerRadii = floatArrayOf(s, s, r, r, r, r, r, r)
            }
            Ui.pad(this, 14, 12, 14, 12)
        }
        bubble.add(Ui.text(this, m.text, 16, 0xFF1D2939.toInt(), lineSpacing = 1.25f))
        bubble.add(Ui.text(this, m.url, 16, C.BLUE, lineSpacing = 1.25f).apply {
            paint.isUnderlineText = true
            setOnClickListener { tap(m.url) }
        })
        list.add(bubble, (resources.displayMetrics.widthPixels * 0.86).toInt())
        list.add(Ui.text(this, m.time, 12, C.G400).apply { setPadding(Ui.dp(context, 4), 0, 0, 0) })
        page.add(ScrollView(this).apply { addView(list); isFillViewport = true; setBackgroundColor(0xFFF7F8FA.toInt()) },
            ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f)

        page.addView(Ui.divider(this))
        val input = Ui.row(this).apply { Ui.pad(this, 14, 10, 14, 10) }
        input.add(Ui.text(this, "문자 메시지", 15, C.G400).apply {
            background = Ui.rounded(context, C.G100, 20)
            minHeight = Ui.dp(context, 40); gravity = Gravity.CENTER_VERTICAL
            setPadding(Ui.dp(context, 16), 0, Ui.dp(context, 16), 0)
        })
        page.add(input)
        return page
    }

    /** 실제 문자 앱에서 링크를 누른 것과 같은 흐름(검사 화면)으로 보낸다 */
    private fun tap(url: String) {
        startActivity(Intent(this, LinkActivity::class.java).setAction(Intent.ACTION_VIEW).setData(Uri.parse(url)))
    }
}
