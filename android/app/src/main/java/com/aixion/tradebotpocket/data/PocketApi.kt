package com.aixion.tradebotpocket.data

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET
import retrofit2.http.Header
import java.util.concurrent.TimeUnit

interface PocketApiService {
    @GET("chart")
    suspend fun getChart(
        @retrofit2.http.Header("X-Aixion-Pocket-Key") apiKey: String,
        @retrofit2.http.Query("index") index: String = "NIFTY"
    ): ChartResponse

    @GET("health")
    suspend fun getHealth(
        @Header("X-Aixion-Pocket-Key") apiKey: String
    ): HealthResponse

    @GET("positions")
    suspend fun getPositions(
        @Header("X-Aixion-Pocket-Key") apiKey: String
    ): PositionsResponse

    @GET("market")
    suspend fun getMarket(
        @Header("X-Aixion-Pocket-Key") apiKey: String
    ): MarketResponse

    @GET("signals")
    suspend fun getSignals(
        @Header("X-Aixion-Pocket-Key") apiKey: String
    ): SignalsResponse
}

object ApiClient {
    private var currentBaseUrl: String = "http://100.68.131.88:8765/"
    private var apiService: PocketApiService? = null

    fun getService(baseUrl: String = currentBaseUrl): PocketApiService {
        val sanitizedUrl = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"
        if (apiService == null || currentBaseUrl != sanitizedUrl) {
            currentBaseUrl = sanitizedUrl

            val logging = HttpLoggingInterceptor().apply {
                level = HttpLoggingInterceptor.Level.BASIC
            }

            val client = OkHttpClient.Builder()
                .connectTimeout(6, TimeUnit.SECONDS)
                .readTimeout(8, TimeUnit.SECONDS)
                .addInterceptor(logging)
                .build()

            val retrofit = Retrofit.Builder()
                .baseUrl(sanitizedUrl)
                .client(client)
                .addConverterFactory(GsonConverterFactory.create())
                .build()

            apiService = retrofit.create(PocketApiService::class.java)
        }
        return apiService!!
    }
}
