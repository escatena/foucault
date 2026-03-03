#include <QMC5883LCompass.h>
#include <math.h>

QMC5883LCompass compass;

// =====================================================
// ================= PINOS =============================
// =====================================================

#define R_PWM 5
#define L_PWM 4
#define R_Enable 3
#define L_Enable 2
#define Led2 8
#define Led1 9

// =====================================================
// ============== ESTADOS ==============================
// =====================================================

enum EstadoEletroima { DESLIGA, PUXA, EMPURRA };
EstadoEletroima estadoEletroima = DESLIGA;

enum EstadoSistema {
  CICLO_INATIVO,
  CICLO_ATIVO
};

EstadoSistema estadoSistema = CICLO_INATIVO;

// =====================================================
// ============== TEMPORIZAÇÃO ORIGINAL =================
// =====================================================

unsigned long tempoPico = 0;
unsigned long tempoEntrePicos = 0;

unsigned long eletroimaEmpurraStart = 0;
unsigned long eletroimaPuxaStart = 0;
unsigned long eletroimaOffTime = 0;

const unsigned long delayEmpurra = 50;
const unsigned long tempoEmpurrando = 200;

const unsigned long delayPuxa = 100;
const unsigned long tempoPuxando = 50;

const unsigned long delayMedida = 350;

const unsigned long tempoMinimoEntrePicos = 700;
const double toleranciaPico = 2;

// =====================================================
// ================= SENSOR ============================
// =====================================================

double x_value, y_value, z_value;
double x_offset = -34;
double y_offset = -195;
double z_offset = 215;

bool medidaPronta = false;
bool medidaFeita = false;
bool OffFlag = false;

double delta_x[2];
double delta_y[2];
int count_angle = 0;
double angulo;
double tempoAngulo;

// =====================================================
// ===================== SETUP =========================
// =====================================================

void setup() {

  Serial.begin(19200);

  compass.init();
  compass.setSmoothing(10, true);
  compass.setCalibrationScales(0.1, 0.1, 0.1);

  pinMode(R_PWM, OUTPUT);
  pinMode(L_PWM, OUTPUT);
  pinMode(L_Enable, OUTPUT);
  pinMode(R_Enable, OUTPUT);
  pinMode(Led1, OUTPUT);
  pinMode(Led2, OUTPUT);

  digitalWrite(L_Enable, HIGH);
  digitalWrite(R_Enable, HIGH);

  delay(1000);
}

// =====================================================
// ===================== LOOP ==========================
// =====================================================

void loop() {
  digitalWrite(Led2, LOW);   

  unsigned long agora = millis();

  atualizarSensor();
  atualizarControle(agora);
  atualizarMedicao(agora);

  PlotXYZ(); 

  medidaFeita = false;
}

// =====================================================
// ============= CONTROLE (TEMPORAL ORIGINAL) =========
// =====================================================

void atualizarControle(unsigned long agora) {

  // Detecta pico exatamente como no original
  if (detectaPico(z_value)) {

    tempoEntrePicos = agora - tempoPico;
    tempoPico = agora;

    eletroimaEmpurraStart = agora + delayEmpurra;
    eletroimaPuxaStart    = agora + tempoEntrePicos / 2 + delayPuxa;

    estadoSistema = CICLO_ATIVO;
    
  }

  if (estadoSistema != CICLO_ATIVO)
    return;

  // ===== EMPURRA =====
  if (agora >= eletroimaEmpurraStart &&
      agora <= eletroimaEmpurraStart + tempoEmpurrando) {

    controlaEletroima(DESLIGA);   // Configurado somente para puxar o pêndulo. Trocar por "EMPURRA" para empurrar.
  }

  // ===== PUXA =====
  else if (agora >= eletroimaPuxaStart &&
           agora <= eletroimaPuxaStart + tempoPuxando) {

    controlaEletroima(PUXA);
  }

  // ===== JANELA MEDIÇÃO =====
  else if (agora >= eletroimaEmpurraStart + tempoEmpurrando &&
           agora < eletroimaPuxaStart) {

    controlaEletroima(DESLIGA);

    if (!OffFlag) {
      eletroimaOffTime = agora;
      OffFlag = true;
    }
  }

  // ===== FIM DO CICLO =====
  else if (agora > eletroimaPuxaStart + tempoPuxando) {

    controlaEletroima(DESLIGA);
    OffFlag = false;
    medidaPronta = false;
    estadoSistema = CICLO_INATIVO;
  }
}

// =====================================================
// ================= MEDIÇÃO SEPARADA ==================
// =====================================================

void atualizarMedicao(unsigned long agora) {

  if (!OffFlag) return;
  if (estadoEletroima != DESLIGA) return;
  if (agora <= eletroimaOffTime + delayMedida) return;
  if (medidaPronta) return;
  

  digitalWrite(Led2, HIGH);

  medidaPronta = true;
  medidaFeita  = true;

  CalculaAngulo(tempoAngulo, angulo);
}

// =====================================================
// ============== DETECÇÃO DE PICO =====================
// =====================================================

bool detectaPico(double valorAtual) {

  static double valorAnterior = 0;
  static bool subindo = false;

  if (abs(valorAtual - valorAnterior) > toleranciaPico) {

    if (valorAtual > valorAnterior)
      subindo = true;

    else if (subindo && valorAtual < valorAnterior) {

      subindo = false;

      if (millis() - tempoPico > tempoMinimoEntrePicos) {
        valorAnterior = valorAtual;
        return true;
      }
    }
  }

  valorAnterior = valorAtual;
  return false;
}

// =====================================================
// ============== CONTROLE ELETROÍMÃ ===================
// =====================================================

void controlaEletroima(EstadoEletroima estado) {

  estadoEletroima = estado;
  switch (estado) {

    case DESLIGA:
      digitalWrite(R_PWM, LOW);
      digitalWrite(L_PWM, LOW);
      digitalWrite(Led1, LOW);
      break;

    case PUXA:
      digitalWrite(R_PWM, LOW);
      digitalWrite(L_PWM, HIGH);
      digitalWrite(Led1, HIGH);
      break;

    case EMPURRA:
      digitalWrite(R_PWM, HIGH);
      digitalWrite(L_PWM, LOW);
      digitalWrite(Led1, HIGH);
      break;
  }
}

// =====================================================
// ================= SENSOR ============================
// =====================================================

void atualizarSensor() {
  compass.read();
  x_value = compass.getX() + x_offset;
  y_value = compass.getY() + y_offset;
  z_value = compass.getZ() + z_offset;
}

// =====================================================
// ================= ÂNGULO ============================
// =====================================================

void CalculaAngulo(double &time_angle, double &angle) {

  delta_x[count_angle] = x_value;
  delta_y[count_angle] = y_value;
  count_angle++;

  if (count_angle < 2) return;

  count_angle = 0;

  if (delta_x[1] == delta_x[0]) return;

  angle = atan((delta_y[1] - delta_y[0]) /
               (delta_x[1] - delta_x[0])) * 180.0 / PI;

  if (angle < 0) angle += 180;

  time_angle = millis();
}

// =====================================================
// ================= SERIAL ============================
// =====================================================

void PlotXYZ() {

  Serial.print(millis());
  Serial.print(" ; ");
  Serial.print(x_value);
  Serial.print(" ; ");
  Serial.print(y_value);
  Serial.print(" ; ");
  Serial.print(z_value);
  Serial.print(" ; ");
  Serial.print(tempoAngulo);
  Serial.print(" ; ");
  Serial.print(angulo);
  Serial.print(" ; ");
  Serial.println(medidaFeita);
}