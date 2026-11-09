plugins {
    id("com.android.application")
}

android {
    namespace = "kr.team4.smishing"
    compileSdk = 37

    defaultConfig {
        applicationId = "kr.team4.smishing"
        minSdk = 29          // 기본 브라우저 역할 요청(RoleManager)이 Android 10부터
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0"
        // 검사 서버 주소. 개발 중엔 'adb reverse tcp:8000 tcp:8000' 후 PC 로컬 서버를 127.0.0.1로 연결.
        // 배포용: gradlew assembleRelease -PapiBase=https://<스페이스주소>.hf.space
        buildConfigField("String", "API_BASE", "\"${project.findProperty("apiBase") ?: "http://127.0.0.1:8000"}\"")
    }

    buildFeatures { buildConfig = true }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
