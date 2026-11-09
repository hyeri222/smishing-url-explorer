package kr.team4.smishing

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.text.TextUtils
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView

/** 디자인(design/스미싱 URL 탐색기.dc.html)의 색 */
object C {
    val BLUE = 0xFF1F4FD8.toInt()
    val BLUE_DARK = 0xFF163AA6.toInt()
    val BLUE_SOFT = 0xFFEAF0FF.toInt()
    val BLUE_TINT = 0xFFD6E0FF.toInt()
    val INK = 0xFF0F1B33.toInt()
    val G700 = 0xFF344054.toInt()
    val G600 = 0xFF475467.toInt()
    val G500 = 0xFF667085.toInt()
    val G400 = 0xFF98A2B3.toInt()
    val G300 = 0xFFD0D5DD.toInt()
    val G200 = 0xFFE4E7EC.toInt()
    val G100 = 0xFFF2F4F7.toInt()
    val BG = 0xFFF3F5F9.toInt()
    val RED = 0xFFD92D20.toInt()
    val RED_TEXT = 0xFFC4320A.toInt()
    val RED_SOFT = 0xFFFEF0EF.toInt()
    val RED_LINE = 0xFFFDA29B.toInt()
    val SCRIM = 0x730F1B33
    val WHITE = Color.WHITE
}

/** 판정별 표시(라벨·배경·글자색) */
enum class Verdict(val key: String, val label: String, val bg: Int, val fg: Int, val source: String) {
    DANGER("danger", "위험", 0xFFFEF0EF.toInt(), 0xFFC4320A.toInt(), "AI 판단"),
    CAUTION("caution", "주의", 0xFFFFF4E0.toInt(), 0xFFB54708.toInt(), "AI 판단"),
    SAFE("safe", "안전", 0xFFECFDF3.toInt(), 0xFF067647.toInt(), "AI 판단"),
    OFFICIAL("official", "공식", 0xFFEAF0FF.toInt(), 0xFF1F4FD8.toInt(), "휴대폰에서 확인"),
    UNKNOWN("unknown", "확인 못 함", 0xFFF2F4F7.toInt(), 0xFF344054.toInt(), "목적지 확인 실패");

    companion object {
        fun of(key: String?) = entries.firstOrNull { it.key == key } ?: UNKNOWN
    }
}

/** Pretendard 글꼴(res/font). 굵기별로 한 번만 불러온다 */
object Fonts {
    private val cache = HashMap<Int, Typeface>()
    fun get(ctx: Context, weight: Int): Typeface = cache.getOrPut(weight) {
        val id = when {
            weight >= 800 -> R.font.pretendard_extrabold
            weight >= 700 -> R.font.pretendard_bold
            weight >= 600 -> R.font.pretendard_semibold
            else -> R.font.pretendard_regular
        }
        try { ctx.resources.getFont(id) } catch (e: Exception) { Typeface.DEFAULT }
    }
}

/** 코드로 화면을 만드는 도우미. 크기는 디자인의 px를 그대로 dp로 쓴다 */
object Ui {
    fun dp(ctx: Context, v: Number) = (v.toFloat() * ctx.resources.displayMetrics.density).toInt()

    fun rounded(ctx: Context, color: Int, radius: Number, stroke: Int? = null, strokeDp: Number = 1) =
        GradientDrawable().apply {
            setColor(color)
            cornerRadius = dp(ctx, radius).toFloat()
            if (stroke != null) setStroke(dp(ctx, strokeDp), stroke)
        }

    /** 위쪽 모서리만 둥근 배경(아래에서 올라오는 시트) */
    fun topRounded(ctx: Context, color: Int, radius: Number) = GradientDrawable().apply {
        setColor(color)
        val r = dp(ctx, radius).toFloat()
        cornerRadii = floatArrayOf(r, r, r, r, 0f, 0f, 0f, 0f)
    }

    fun ripple(bg: android.graphics.drawable.Drawable, pressed: Int = 0x22000000) =
        RippleDrawable(ColorStateList.valueOf(pressed), bg, null)

    fun text(ctx: Context, s: CharSequence, size: Number = 15, color: Int = C.INK, weight: Int = 400,
             mono: Boolean = false, lineSpacing: Float = 1.0f, center: Boolean = false) = TextView(ctx).apply {
        text = s
        textSize = size.toFloat()
        setTextColor(color)
        typeface = if (mono) Typeface.MONOSPACE else Fonts.get(ctx, weight)
        includeFontPadding = false
        setLineSpacing(0f, lineSpacing)
        if (center) gravity = Gravity.CENTER
        if (mono) letterSpacing = -0.02f
    }

    fun ellipsize(tv: TextView) = tv.apply { maxLines = 1; ellipsize = TextUtils.TruncateAt.END }

    fun col(ctx: Context, gapDp: Int = 0) = LinearLayout(ctx).apply {
        orientation = LinearLayout.VERTICAL
        if (gapDp > 0) showDividers(this, gapDp, vertical = true)
    }

    fun row(ctx: Context, gapDp: Int = 0, center: Boolean = true) = LinearLayout(ctx).apply {
        orientation = LinearLayout.HORIZONTAL
        if (center) gravity = Gravity.CENTER_VERTICAL
        if (gapDp > 0) showDividers(this, gapDp, vertical = false)
    }

    /** 자식 사이 간격(CSS의 gap) */
    private fun showDividers(l: LinearLayout, gapDp: Int, vertical: Boolean) {
        val px = dp(l.context, gapDp)
        l.dividerDrawable = GradientDrawable().apply {
            setColor(Color.TRANSPARENT)
            if (vertical) setSize(1, px) else setSize(px, 1)
        }
        l.showDividers = LinearLayout.SHOW_DIVIDER_MIDDLE
    }

    fun pad(v: View, l: Int, t: Int, r: Int, b: Int) = v.apply {
        setPadding(dp(context, l), dp(context, t), dp(context, r), dp(context, b))
    }

    fun pad(v: View, all: Int) = pad(v, all, all, all, all)

    // ---- LayoutParams 도우미 ----
    fun LinearLayout.add(v: View, w: Int = ViewGroup.LayoutParams.MATCH_PARENT,
                         h: Int = ViewGroup.LayoutParams.WRAP_CONTENT, weight: Float = 0f): View {
        addView(v, LinearLayout.LayoutParams(w, h, weight))
        return v
    }

    fun LinearLayout.addSized(v: View, wDp: Int, hDp: Int): View {
        addView(v, LinearLayout.LayoutParams(dp(context, wDp), dp(context, hDp)))
        return v
    }

    fun FrameLayout.addFill(v: View): View {
        addView(v, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        return v
    }

    fun spacer(ctx: Context) = View(ctx)

    // ---- 버튼 ----
    fun primaryButton(ctx: Context, s: String, heightDp: Int = 60, size: Number = 19, bg: Int = C.BLUE,
                      radius: Int = 16, onClick: () -> Unit) = text(ctx, s, size, C.WHITE, 700, center = true).apply {
        background = ripple(rounded(ctx, bg, radius), 0x33FFFFFF)
        minHeight = dp(ctx, heightDp)
        isClickable = true
        setOnClickListener { onClick() }
    }

    fun outlineButton(ctx: Context, s: String, heightDp: Int = 60, size: Number = 17, onClick: () -> Unit) =
        text(ctx, s, size, C.INK, 700, center = true).apply {
            background = ripple(rounded(ctx, C.WHITE, 16, C.G300))
            minHeight = dp(ctx, heightDp)
            setOnClickListener { onClick() }
        }

    fun linkButton(ctx: Context, s: String, heightDp: Int = 44, onClick: () -> Unit) =
        text(ctx, s, 14, C.G500, center = true).apply {
            paint.isUnderlineText = true
            minHeight = dp(ctx, heightDp)
            setOnClickListener { onClick() }
        }

    /** 판정 배지(위험·주의·안전·공식·확인 못 함) */
    fun badge(ctx: Context, v: Verdict, size: Number = 13, minWDp: Int = 58, hDp: Int = 28) =
        text(ctx, v.label, size, v.fg, 700, center = true).apply {
            background = rounded(ctx, v.bg, 8)
            minWidth = dp(ctx, minWDp)
            minHeight = dp(ctx, hDp)
            setPadding(dp(ctx, 8), 0, dp(ctx, 8), 0)
        }

    /** 숫자가 든 동그라미(1, 2, 3 단계 표시) */
    fun numDot(ctx: Context, s: String, bg: Int, fg: Int, sizeDp: Int = 24) =
        text(ctx, s, 13, fg, 800, center = true).apply {
            background = rounded(ctx, bg, sizeDp / 2)
            layoutParams = LinearLayout.LayoutParams(dp(ctx, sizeDp), dp(ctx, sizeDp))
        }

    fun card(ctx: Context, radius: Int = 18, gapDp: Int = 0) = col(ctx, gapDp).apply {
        background = rounded(ctx, C.WHITE, radius, C.G200)
        clipToOutline = true
    }

    fun divider(ctx: Context) = View(ctx).apply {
        setBackgroundColor(C.G100)
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(ctx, 1))
    }

    fun icon(ctx: Context, res: Int, sizeDp: Int) = android.widget.ImageView(ctx).apply {
        setImageResource(res)
        layoutParams = LinearLayout.LayoutParams(dp(ctx, sizeDp), dp(ctx, sizeDp))
    }

    /** 둥근 사각형 안에 아이콘 */
    fun iconTile(ctx: Context, res: Int, tileDp: Int, iconDp: Int, bg: Int, radius: Int) = FrameLayout(ctx).apply {
        background = rounded(ctx, bg, radius)
        addView(android.widget.ImageView(ctx).apply { setImageResource(res) },
            FrameLayout.LayoutParams(dp(ctx, iconDp), dp(ctx, iconDp), Gravity.CENTER))
        layoutParams = LinearLayout.LayoutParams(dp(ctx, tileDp), dp(ctx, tileDp))
    }
}
