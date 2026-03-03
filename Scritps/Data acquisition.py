import serial
import csv
import datetime
import os
import collections
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import threading
from matplotlib.patches import Patch  # Importar Patch para criar a legenda manualmente
import matplotlib.text as mtext

class LegendTitle(object):
    def __init__(self, text_props=None):
        self.text_props = text_props or {}
        super(LegendTitle, self).__init__()

    def legend_artist(self, legend, orig_handle, fontsize, handlebox):
        x0, y0 = handlebox.xdescent, handlebox.ydescent
        title = mtext.Text(x0, y0, r'\underline{' + orig_handle + '}', usetex=True, **self.text_props)
        handlebox.add_artist(title)
        return title

# Configurações da comunicação serial
PORT = "/dev/ttyACM0"
BAUD_RATE = 19200
OUTPUT_FILE = "dados_arduino.csv"
OUTPUT_ANGLE_FILE = "angulo_filtrado.csv"

# Cabeçalhos dos arquivos CSV
HEADERS = ["Data", "Tempo", "X", "Y", "Z", "Tempo Ângulo", "Ângulo", "Trigger"]
HEADERS_ANGLE = ["Data", "Tempo Ângulo", "Ângulo", "\u03b8_m", "Desvio Padrão","Coef. Angular"]

# Variáveis globais
ultimo_angulo = None
pulou = False
theta_amostras = collections.deque(maxlen=20)
theta_media_data, theta_std_data, tempo_data = [], [], []
data_lock = threading.Lock()  # Lock para sincronização de threads

def save_to_csv(data, file_name, headers):
    file_exists = os.path.exists(file_name)
    try:
        with open(file_name, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow(headers)
            writer.writerow(data)
    except IOError as e:
        print(f"Erro ao salvar no CSV: {e}")

def process_angle_data(tempoAngulo, angulo):
    global ultimo_angulo, pulou
    if angulo != ultimo_angulo:
        if pulou:
            theta_amostras.append(angulo)
            ultimo_angulo = angulo
            pulou = False
            theta_m = np.mean(theta_amostras)
            theta_std = np.std(theta_amostras, ddof=1) / np.sqrt(len(theta_amostras)) if len(theta_amostras) > 1 else 0
            with data_lock:
                tempo_data.append(tempoAngulo)
                theta_media_data.append(theta_m)
                theta_std_data.append(theta_std)
                inclinacao, intercepto = calcular_regressao_linear(tempo_data, theta_media_data)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_to_csv([timestamp, tempoAngulo, angulo, round(theta_m, 2), round(theta_std, 2), round(inclinacao,3)], OUTPUT_ANGLE_FILE, HEADERS_ANGLE)
            print(f"🔹 Ângulo: {angulo:.2f}, Média Móvel (θ_m): {theta_m:.2f}, Desvio Padrão: {theta_std:.2f}, Coef. Angular: {inclinacao:.3f}")
        else:
            pulou = True

def read_serial():
    try:
        with serial.Serial(PORT, BAUD_RATE, timeout=1) as ser:
            print("Lendo dados da porta serial... Pressione Ctrl+C para sair.")
            while True:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                parts = line.split(";")
                if len(parts) != 7:
                    print(f"Dado inválido recebido: {line}")
                    continue
                try:
                    tempo, x, y, z, tempoAngulo, angulo, trigger = map(float, parts)
                    print(f"Tempo: {tempo:.2f}, X: {x:.2f}, Y: {y:.2f}, Z: {z:.2f}, Tempo Ângulo: {tempoAngulo:.2f}, Ângulo: {angulo:.2f}, Trigger: {trigger:.0f}")
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    save_to_csv([timestamp, tempo, x, y, z, tempoAngulo, angulo, trigger], OUTPUT_FILE, HEADERS)
                    if trigger == 1:
                        process_angle_data(tempoAngulo, angulo)
                except ValueError:
                    print(f"Erro ao converter os dados: {line}")
    except serial.SerialException as e:
        print(f"Erro ao acessar a porta serial: {e}")

# Configuração do gráfico
fig, ax = plt.subplots(figsize=(8, 5))
line_m, = ax.plot([], [], 'b-', label=r'$\theta_m$ (Moving average)')
ax.set_xlabel("Time (hour)")
ax.set_ylabel("Oscillation's plane angle (°)")
ax.set_title("Moving average and Standard Deviation of $\\theta$")
text_info = ax.text(0.05, 0.95, '', transform=ax.transAxes, fontsize=10, verticalalignment='top', 
                    bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

def calcular_regressao_linear(tempo_data, theta_media_data):
    """
    Calcula a regressão linear dos dados de ângulo em função do tempo.
    Retorna a inclinação (graus/hora) e o intercepto.
    """
    # Converter o tempo para horas
    tempo_segundos = np.array(tempo_data) / 3600000  # Supondo que o tempo esteja em milissegundos
    
    # Ajustar uma linha aos dados (regressão linear)
    coeficientes = np.polyfit(tempo_segundos, theta_media_data, 1)
    inclinacao = coeficientes[0]  # Coeficiente angular (graus/hora)
    intercepto = coeficientes[1]  # Coeficiente linear
    
    return inclinacao, intercepto

def update_plot(frame):
    with data_lock:
        if not tempo_data or not theta_media_data:
            return line_m, text_info
        
        # Atualizar os dados da linha
        line_m.set_data(np.array(tempo_data) / 3600000, theta_media_data)
        
        # Limpar preenchimentos anteriores e adicionar o novo desvio padrão
        for collection in ax.collections:
            collection.remove()
        ax.fill_between(np.array(tempo_data) / 3600000, np.array(theta_media_data) - np.array(theta_std_data),
                        np.array(theta_media_data) + np.array(theta_std_data), color='b', alpha=0.2)
        
        # Calcular a regressão linear
        inclinacao, intercepto = calcular_regressao_linear(tempo_data, theta_media_data)
        
        # Atualizar a legenda
        patch = Patch(color='blue', alpha=0.2, label=r'$\sigma_\theta$ (Standard Deviation)')
        ax.legend(handles=[line_m, patch], labels=[r'$\theta_m$ (Moving Average)', r'$\sigma_\theta$ (Standard Deviation)'],
                  handler_map={str: LegendTitle({'fontsize': 12})}, loc='upper right')
        
        # Atualizar limites dos eixos
        ax.set_xlim(min(tempo_data) / 3600000, max(tempo_data) / 3600000)
        ax.set_ylim(min(theta_media_data) - 5, max(theta_media_data) + 5)
        
        # Atualizando as informações de texto
        ultimo_tempo = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text_info.set_text(f"Last measurement: {ultimo_tempo}\n"
                           f"$\\theta$: {theta_amostras[-1]:.2f}°\n"
                           f"$\\theta_m$: {theta_media_data[-1]:.2f}°\n"
                           f"Standard Deviation: {theta_std_data[-1]:.2f}°\n"
                           f"Precession speed: {inclinacao:.3f}°/h")
    
    return line_m, text_info

if __name__ == "__main__":
    serial_thread = threading.Thread(target=read_serial, daemon=True)
    serial_thread.start()
    ani = FuncAnimation(fig, update_plot, interval=1000, blit=False)
    plt.show()
