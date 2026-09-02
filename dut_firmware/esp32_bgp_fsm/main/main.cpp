#include <string.h>
#include <sys/param.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "esp_netif.h"
#include "lwip/err.h"
#include "lwip/sockets.h"

#define WIFI_SSID      "Yettel_67B96C"
#define WIFI_PASS      "dY2hy3eS"
#define PORT           179

static const char *TAG = "BGP_FSM";

enum BGP_State {
    BGP_IDLE,
    BGP_CONNECT,
    BGP_ACTIVE,
    BGP_OPENSENT,
    BGP_ESTABLISHED
};

static BGP_State currentState = BGP_IDLE;

// Use explicit spacing inside brackets to avoid markdown parsing issues
const uint8_t EXPECTED_MARKER[ 16 ] = {
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF
};

void printState(BGP_State state) {
    switch (state) {
        case BGP_IDLE: ESP_LOGI(TAG, "STATE: IDLE"); break;
        case BGP_CONNECT: ESP_LOGI(TAG, "STATE: CONNECT"); break;
        case BGP_ACTIVE: ESP_LOGI(TAG, "STATE: ACTIVE"); break;
        case BGP_OPENSENT: ESP_LOGI(TAG, "STATE: OPENSENT"); break;
        case BGP_ESTABLISHED: ESP_LOGI(TAG, "STATE: ESTABLISHED"); break;
    }
}

static void wifi_event_handler(void* arg, esp_event_base_t event_base,
                                int32_t event_id, void* event_data) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "WiFi connection lost. Reconnecting...");
        esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t* event = (ip_event_got_ip_t*) event_data;
        ESP_LOGI(TAG, "WiFi Connected. IP Address: " IPSTR, IP2STR(&event->ip_info.ip));
        currentState = BGP_CONNECT;
        printState(currentState);
    }
}

void wifi_init_sta(void) {
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    esp_event_handler_instance_t instance_any_id;
    esp_event_handler_instance_t instance_got_ip;
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
                                                        ESP_EVENT_ANY_ID,
                                                        &wifi_event_handler,
                                                        NULL,
                                                        &instance_any_id));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT,
                                                        IP_EVENT_STA_GOT_IP,
                                                        &wifi_event_handler,
                                                        NULL,
                                                        &instance_got_ip));

    wifi_config_t wifi_config = {};
    strcpy((char*)wifi_config.sta.ssid, WIFI_SSID);
    strcpy((char*)wifi_config.sta.password, WIFI_PASS);

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());
}

static void bgp_server_task(void *pvParameters) {
    char addr_str[ 64 ];
    int listen_sock = socket(AF_INET, SOCK_STREAM, IPPROTO_IP);
    if (listen_sock < 0) {
        ESP_LOGE(TAG, "Unable to create socket");
        vTaskDelete(NULL);
    }

    int opt = 1;
    setsockopt(listen_sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in dest_addr;
    dest_addr.sin_addr.s_addr = htonl(INADDR_ANY);
    dest_addr.sin_family = AF_INET;
    dest_addr.sin_port = htons(PORT);

    if (bind(listen_sock, (struct sockaddr *)&dest_addr, sizeof(dest_addr)) != 0) {
        ESP_LOGE(TAG, "Socket unable to bind");
        close(listen_sock);
        vTaskDelete(NULL);
    }

    if (listen(listen_sock, 1) != 0) {
        ESP_LOGE(TAG, "Error occurred during listen");
        close(listen_sock);
        vTaskDelete(NULL);
    }

    while (1) {
        struct sockaddr_storage source_addr;
        socklen_t addr_len = sizeof(source_addr);
        int sock = accept(listen_sock, (struct sockaddr *)&source_addr, &addr_len);
        if (sock < 0) {
            ESP_LOGE(TAG, "Unable to accept connection");
            break;
        }

        inet_ntoa_r(((struct sockaddr_in *)&source_addr)->sin_addr, addr_str, sizeof(addr_str) - 1);
        ESP_LOGI(TAG, "TCP client connected from: %s", addr_str);
        currentState = BGP_ACTIVE;
        printState(currentState);

        while (1) {
            uint8_t rx_buffer[ 1024 ]; // Ispravno definisan niz od 1024 bajta
            int len = recv(sock, rx_buffer, sizeof(rx_buffer), 0);
            if (len < 0) {
                ESP_LOGE(TAG, "recv failed");
                break;
            } else if (len == 0) {
                ESP_LOGI(TAG, "Connection closed");
                break;
            } else {
                if (len >= 19) {
                    bool markerValid = true;
                    for (int i = 0; i < 16; i++) {
                        if (rx_buffer[ i ] != EXPECTED_MARKER[ i ]) {
                            markerValid = false;
                            break;
                        }
                    }

                    if (!markerValid) {
                        ESP_LOGE(TAG, "[ERROR_INJECTION] Invalid Marker received!");
                        send(sock, "ERR_BAD_MARKER\n", 15, 0);
                        currentState = BGP_IDLE;
                        printState(currentState);
                        vTaskDelay(pdMS_TO_TICKS(2000));
                        currentState = BGP_CONNECT;
                        printState(currentState);
                        break;
                    }

                    // Parse packet length (bytes 16 and 17) and type (byte 18)
                    uint16_t bgp_len = (rx_buffer[ 16 ] << 8) | rx_buffer[ 17 ];
                    uint8_t type = rx_buffer[ 18 ];

                    ESP_LOGI(TAG, "Valid BGP Header. Length: %d, Type: %d", bgp_len, type);

                    if (type == 1) { // OPEN Message
                        currentState = BGP_OPENSENT;
                        printState(currentState);
                        send(sock, "ACK_OPEN\n", 9, 0);
                        vTaskDelay(pdMS_TO_TICKS(500));
                        currentState = BGP_ESTABLISHED;
                        printState(currentState);
                        send(sock, "ADI_BGP_SESSION_ESTABLISHED\n", 28, 0);
                    }
                }
            }
        }

        close(sock);
        ESP_LOGI(TAG, "TCP Connection cleaned up.");
        if (currentState != BGP_IDLE) {
            currentState = BGP_CONNECT;
            printState(currentState);
        }
    }
    close(listen_sock);
    vTaskDelete(NULL);
}

extern "C" void app_main(void) {
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
      ESP_ERROR_CHECK(nvs_flash_erase());
      ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    ESP_LOGI(TAG, "=================================================");
    ESP_LOGI(TAG, "HIL-NetLink: BGP FSM Target Online");
    ESP_LOGI(TAG, "=================================================");

    wifi_init_sta();

    xTaskCreate(bgp_server_task, "bgp_server", 4096, NULL, 5, NULL);
}
