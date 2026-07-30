/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/

/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

TIM_HandleTypeDef htim2;
TIM_HandleTypeDef htim3;
TIM_HandleTypeDef htim4;
TIM_HandleTypeDef htim8;

/* USER CODE BEGIN PV */

//Motor1
//PWM     : TIM3 CH1 / CH2
//Encoder : TIM2
//Enable  : PB8 / PB9

//Motor2
//PWM     : TIM4 CH1 / CH2
//Encoder : TIM8
//Enable  : PA9 / PA8

/* =========================================================
 * Motor1 Encoder Variables
 * - TIM2 엔코더의 현재값, 변화량, 누적값을 저장
 * ========================================================= */
volatile uint16_t motor1_encoder_raw = 0;
volatile uint16_t motor1_previous_count = 0;
volatile int16_t  motor1_encoder_delta = 0;
volatile int32_t  motor1_encoder_total = 0;


/* =========================================================
 * Motor2 Encoder Variables
 * - TIM8 엔코더의 현재값, 변화량, 누적값을 저장
 * ========================================================= */
volatile uint16_t motor2_encoder_raw = 0;
volatile uint16_t motor2_previous_count = 0;
volatile int16_t  motor2_encoder_delta = 0;
volatile int32_t  motor2_encoder_total = 0;


/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_TIM3_Init(void);
static void MX_TIM2_Init(void);
static void MX_TIM4_Init(void);
static void MX_TIM8_Init(void);
/* USER CODE BEGIN PFP */

/* 기본 주행 함수 */
static void Motor_Forward(uint16_t pwm);
static void Motor_Backward(uint16_t pwm);
static void Motor_TurnRight(uint16_t pwm);
static void Motor_TurnLeft(uint16_t pwm);
static void Motor_Stop(void);

/* 지정 시간 동안 엔코더를 계속 갱신 */
static void Motor_WaitAndUpdateEncoder(uint32_t duration_ms);


/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/**
 * @brief PWM 값을 TIM3/TIM4의 범위인 0~99로 제한
 */
static uint16_t Motor_LimitPwm(uint16_t pwm)
{
    if (pwm > 99)
    {
        pwm = 99;
    }

    return pwm;
}


/**
 * @brief 로봇 전진
 *
 * 왼쪽 모터:
 * - TIM3 CH2를 사용해야 차체 기준 전진
 *
 * 오른쪽 모터:
 * - TIM4 CH1을 사용해야 차체 기준 전진
 */
static void Motor_Forward(uint16_t pwm)
{
    pwm = Motor_LimitPwm(pwm);

    /* Motor1: 왼쪽 모터 전진 */
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, pwm);

    /* Motor2: 오른쪽 모터 전진 */
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, pwm);
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, 0);
}


/**
 * @brief 로봇 후진
 *
 * 왼쪽과 오른쪽 모터를 전진의 반대 방향으로 회전
 */
static void Motor_Backward(uint16_t pwm)
{
    pwm = Motor_LimitPwm(pwm);

    /* Motor1: 왼쪽 모터 후진 */
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, pwm);
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);

    /* Motor2: 오른쪽 모터 후진 */
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, pwm);
}


/**
 * @brief 제자리 우회전
 *
 * 왼쪽 바퀴는 전진하고 오른쪽 바퀴는 후진
 */
static void Motor_TurnRight(uint16_t pwm)
{
    pwm = Motor_LimitPwm(pwm);

    /* Motor1: 왼쪽 모터 전진 */
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, pwm);

    /* Motor2: 오른쪽 모터 후진 */
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, pwm);
}


/**
 * @brief 제자리 좌회전
 *
 * 왼쪽 바퀴는 후진하고 오른쪽 바퀴는 전진
 */
static void Motor_TurnLeft(uint16_t pwm)
{
    pwm = Motor_LimitPwm(pwm);

    /* Motor1: 왼쪽 모터 후진 */
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, pwm);
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);

    /* Motor2: 오른쪽 모터 전진 */
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, pwm);
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, 0);
}


/**
 * @brief 좌우 모터 즉시 정지
 */
static void Motor_Stop(void)
{
    /* Motor1: 왼쪽 모터 정지 */
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);

    /* Motor2: 오른쪽 모터 정지 */
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, 0);
}


/**
 * @brief 지정된 시간 동안 엔코더 값을 10ms마다 갱신
 *
 * 단순 HAL_Delay(10000)을 사용하면 그동안 엔코더 변수를
 * 갱신하지 못하므로, 10ms 단위로 카운트를 읽는다.
 */
static void Motor_WaitAndUpdateEncoder(uint32_t duration_ms)
{
    uint32_t start_time = HAL_GetTick();

    while ((HAL_GetTick() - start_time) < duration_ms)
    {
        /* ================================================
         * Motor1: 왼쪽 모터 엔코더 갱신
         * - TIM2 사용
         * ================================================ */
        motor1_encoder_raw =
            (uint16_t)__HAL_TIM_GET_COUNTER(&htim2);

        motor1_encoder_delta =
            (int16_t)(motor1_encoder_raw -
                      motor1_previous_count);

        motor1_previous_count =
            motor1_encoder_raw;

        motor1_encoder_total +=
            motor1_encoder_delta;


        /* ================================================
         * Motor2: 오른쪽 모터 엔코더 갱신
         * - TIM8 사용
         * ================================================ */
        motor2_encoder_raw =
            (uint16_t)__HAL_TIM_GET_COUNTER(&htim8);

        motor2_encoder_delta =
            (int16_t)(motor2_encoder_raw -
                      motor2_previous_count);

        motor2_previous_count =
            motor2_encoder_raw;

        motor2_encoder_total +=
            motor2_encoder_delta;

        HAL_Delay(10);
    }
}


/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_TIM3_Init();
  MX_TIM2_Init();
  MX_TIM4_Init();
  MX_TIM8_Init();
  /* USER CODE BEGIN 2 */

  /* =========================================================
   * Motor1 PWM Start
   * - TIM3 CH1: Motor1 RPWM
   * - TIM3 CH2: Motor1 LPWM
   * ========================================================= */
  HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_1);
  HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_2);


  /* =========================================================
   * Motor2 PWM Start
   * - TIM4 CH1: Motor2 RPWM
   * - TIM4 CH2: Motor2 LPWM
   * ========================================================= */
  HAL_TIM_PWM_Start(&htim4, TIM_CHANNEL_1);
  HAL_TIM_PWM_Start(&htim4, TIM_CHANNEL_2);


  /* =========================================================
   * Motor1 Encoder Start
   * - TIM2 CH1/CH2를 Encoder Mode로 시작
   * ========================================================= */
  HAL_TIM_Encoder_Start(&htim2, TIM_CHANNEL_ALL);


  /* =========================================================
   * Motor2 Encoder Start
   * - TIM8 CH1/CH2를 Encoder Mode로 시작
   * ========================================================= */
  HAL_TIM_Encoder_Start(&htim8, TIM_CHANNEL_ALL);


  /* =========================================================
   * Motor1 Encoder Initialization
   * - TIM2 카운터 및 소프트웨어 누적 변수를 0으로 초기화
   * ========================================================= */
  __HAL_TIM_SET_COUNTER(&htim2, 0);

  motor1_encoder_raw = 0;
  motor1_previous_count = 0;
  motor1_encoder_delta = 0;
  motor1_encoder_total = 0;


  /* =========================================================
   * Motor2 Encoder Initialization
   * - TIM8 카운터 및 소프트웨어 누적 변수를 0으로 초기화
   * ========================================================= */
  __HAL_TIM_SET_COUNTER(&htim8, 0);

  motor2_encoder_raw = 0;
  motor2_previous_count = 0;
  motor2_encoder_delta = 0;
  motor2_encoder_total = 0;


  /* =========================================================
   * Motor1 BTS7960 Enable
   * - PB8: R_EN
   * - PB9: L_EN
   * ========================================================= */
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_8, GPIO_PIN_SET);
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_9, GPIO_PIN_SET);


  /* =========================================================
   * Motor2 BTS7960 Enable
   * - PA9: R_EN
   * - PA8: L_EN
   * ========================================================= */
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_9, GPIO_PIN_SET);
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, GPIO_PIN_SET);


  /* =========================================================
   * Motor1 Initial Stop
   * - RPWM과 LPWM을 모두 0으로 설정
   * ========================================================= */
  __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0);
  __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);


  /* =========================================================
   * Motor2 Initial Stop
   * - RPWM과 LPWM을 모두 0으로 설정
   * ========================================================= */
  __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, 0);
  __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, 0);


  /* USER CODE END 2 */

  /* Initialize leds */
  BSP_LED_Init(LED2);

  /* Initialize USER push-button, will be used to trigger an interrupt each time it's pressed.*/
  BSP_PB_Init(BUTTON_USER, BUTTON_MODE_EXTI);

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
      /* ================================================
       * 1. 전진 테스트
       * - 40% 출력으로 10초 전진
       * ================================================ */
      Motor_Forward(40);
      Motor_WaitAndUpdateEncoder(10000);

      Motor_Stop();
      HAL_Delay(2000);


      /* ================================================
       * 2. 후진 테스트
       * - 40% 출력으로 10초 후진
       * ================================================ */
      Motor_Backward(40);
      Motor_WaitAndUpdateEncoder(10000);

      Motor_Stop();
      HAL_Delay(2000);


      /* ================================================
       * 3. 우회전 테스트
       * - 제자리 우회전을 10초 수행
       * ================================================ */
      Motor_TurnRight(40);
      Motor_WaitAndUpdateEncoder(10000);

      Motor_Stop();
      HAL_Delay(2000);


      /* ================================================
       * 4. 좌회전 테스트
       * - 제자리 좌회전을 10초 수행
       * ================================================ */
      Motor_TurnLeft(40);
      Motor_WaitAndUpdateEncoder(10000);

      Motor_Stop();


      /* 모든 테스트가 끝난 뒤 정지 상태 유지 */
      while (1)
      {
          Motor_Stop();
          HAL_Delay(100);
      }

    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE3);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = 16;
  RCC_OscInitStruct.PLL.PLLN = 336;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV4;
  RCC_OscInitStruct.PLL.PLLQ = 2;
  RCC_OscInitStruct.PLL.PLLR = 2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief TIM2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM2_Init(void)
{

  /* USER CODE BEGIN TIM2_Init 0 */

  /* USER CODE END TIM2_Init 0 */

  TIM_Encoder_InitTypeDef sConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  /* USER CODE BEGIN TIM2_Init 1 */

  /* USER CODE END TIM2_Init 1 */
  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 0;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 65535;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  sConfig.EncoderMode = TIM_ENCODERMODE_TI12;
  sConfig.IC1Polarity = TIM_ICPOLARITY_RISING;
  sConfig.IC1Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC1Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC1Filter = 8;
  sConfig.IC2Polarity = TIM_ICPOLARITY_RISING;
  sConfig.IC2Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC2Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC2Filter = 8;
  if (HAL_TIM_Encoder_Init(&htim2, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM2_Init 2 */

  /* USER CODE END TIM2_Init 2 */

}

/**
  * @brief TIM3 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM3_Init(void)
{

  /* USER CODE BEGIN TIM3_Init 0 */

  /* USER CODE END TIM3_Init 0 */

  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};
  TIM_OC_InitTypeDef sConfigOC = {0};

  /* USER CODE BEGIN TIM3_Init 1 */

  /* USER CODE END TIM3_Init 1 */
  htim3.Instance = TIM3;
  htim3.Init.Prescaler = 89;
  htim3.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim3.Init.Period = 99;
  htim3.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim3.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim3) != HAL_OK)
  {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim3, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_Init(&htim3) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim3, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigOC.OCMode = TIM_OCMODE_PWM1;
  sConfigOC.Pulse = 0;
  sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
  sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
  if (HAL_TIM_PWM_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_1) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM3_Init 2 */

  /* USER CODE END TIM3_Init 2 */
  HAL_TIM_MspPostInit(&htim3);

}

/**
  * @brief TIM4 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM4_Init(void)
{

  /* USER CODE BEGIN TIM4_Init 0 */

  /* USER CODE END TIM4_Init 0 */

  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};
  TIM_OC_InitTypeDef sConfigOC = {0};

  /* USER CODE BEGIN TIM4_Init 1 */

  /* USER CODE END TIM4_Init 1 */
  htim4.Instance = TIM4;
  htim4.Init.Prescaler = 89;
  htim4.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim4.Init.Period = 99;
  htim4.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim4.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim4) != HAL_OK)
  {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim4, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_Init(&htim4) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim4, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigOC.OCMode = TIM_OCMODE_PWM1;
  sConfigOC.Pulse = 0;
  sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
  sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
  if (HAL_TIM_PWM_ConfigChannel(&htim4, &sConfigOC, TIM_CHANNEL_1) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_ConfigChannel(&htim4, &sConfigOC, TIM_CHANNEL_2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM4_Init 2 */

  /* USER CODE END TIM4_Init 2 */
  HAL_TIM_MspPostInit(&htim4);

}

/**
  * @brief TIM8 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM8_Init(void)
{

  /* USER CODE BEGIN TIM8_Init 0 */

  /* USER CODE END TIM8_Init 0 */

  TIM_Encoder_InitTypeDef sConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  /* USER CODE BEGIN TIM8_Init 1 */

  /* USER CODE END TIM8_Init 1 */
  htim8.Instance = TIM8;
  htim8.Init.Prescaler = 0;
  htim8.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim8.Init.Period = 65535;
  htim8.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim8.Init.RepetitionCounter = 0;
  htim8.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  sConfig.EncoderMode = TIM_ENCODERMODE_TI12;
  sConfig.IC1Polarity = TIM_ICPOLARITY_RISING;
  sConfig.IC1Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC1Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC1Filter = 0;
  sConfig.IC2Polarity = TIM_ICPOLARITY_RISING;
  sConfig.IC2Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC2Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC2Filter = 0;
  if (HAL_TIM_Encoder_Init(&htim8, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim8, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM8_Init 2 */

  /* USER CODE END TIM8_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8|GPIO_PIN_9, GPIO_PIN_RESET);

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_8|GPIO_PIN_9, GPIO_PIN_RESET);

  /*Configure GPIO pins : USART_TX_Pin USART_RX_Pin */
  GPIO_InitStruct.Pin = USART_TX_Pin|USART_RX_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF7_USART2;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /*Configure GPIO pins : PA8 PA9 */
  GPIO_InitStruct.Pin = GPIO_PIN_8|GPIO_PIN_9;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /*Configure GPIO pins : PB8 PB9 */
  GPIO_InitStruct.Pin = GPIO_PIN_8|GPIO_PIN_9;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
