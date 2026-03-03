import serial
import csv
import datetime
import os
import collections
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import threading
from matplotlib.patches import Patch
import matplotlib.text as mtext


# =====================================================
# =============== CUSTOM LEGEND TITLE =================
# =====================================================

class LegendTitle(object):
    def __init__(self, text_props=None):
        self.text_props = text_props or {}
        super(LegendTitle, self).__init__()

    def legend_artist(self, legend, orig_handle, fontsize, handlebox):
        x0, y0 = handlebox.xdescent, handlebox.ydescent
        title = mtext.Text(
            x0, y0,
            r'\underline{' + orig_handle + '}',
            usetex=True,
            **self.text_props
        )
        handlebox.add_artist(title)
        return title


# =====================================================
# =============== SERIAL CONFIGURATION ================
# =====================================================

SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 19200
RAW_OUTPUT_FILE = "arduino_data.csv"
ANGLE_OUTPUT_FILE = "filtered_angle.csv"


# CSV headers
RAW_HEADERS = ["Date", "Time", "X", "Y", "Z", "Angle Time", "Angle", "Trigger"]
ANGLE_HEADERS = ["Date", "Angle Time", "Angle", "θ_m", "Standard Deviation", "Slope"]


# =====================================================
# =============== GLOBAL VARIABLES ====================
# =====================================================

last_angle = None
skip_next = False

angle_samples = collections.deque(maxlen=20)

theta_mean_data = []
theta_std_data = []
time_data = []

data_lock = threading.Lock()


# =====================================================
# =============== CSV SAVE FUNCTION ===================
# =====================================================

def save_to_csv(data, file_name, headers):
    file_exists = os.path.exists(file_name)

    try:
        with open(file_name, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)

            if not file_exists:
                writer.writerow(headers)

            writer.writerow(data)

    except IOError as e:
        print(f"Error saving CSV file: {e}")


# =====================================================
# =============== ANGLE PROCESSING ====================
# =====================================================

def process_angle_data(angle_time, angle_value):
    global last_angle, skip_next

    if angle_value != last_angle:

        if skip_next:

            angle_samples.append(angle_value)
            last_angle = angle_value
            skip_next = False

            theta_mean = np.mean(angle_samples)
            theta_std = (
                np.std(angle_samples, ddof=1) / np.sqrt(len(angle_samples))
                if len(angle_samples) > 1 else 0
            )

            with data_lock:
                time_data.append(angle_time)
                theta_mean_data.append(theta_mean)
                theta_std_data.append(theta_std)

                slope, intercept = calculate_linear_regression(
                    time_data, theta_mean_data
                )

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            save_to_csv(
                [timestamp, angle_time, angle_value,
                 round(theta_mean, 2),
                 round(theta_std, 2),
                 round(slope, 3)],
                ANGLE_OUTPUT_FILE,
                ANGLE_HEADERS
            )

            print(
                f"Angle: {angle_value:.2f}, "
                f"Moving Average (θ_m): {theta_mean:.2f}, "
                f"Standard Deviation: {theta_std:.2f}, "
                f"Slope: {slope:.3f}"
            )

        else:
            skip_next = True


# =====================================================
# =============== SERIAL READING ======================
# =====================================================

def read_serial():

    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:

            print("Reading serial data... Press Ctrl+C to exit.")

            while True:

                line = ser.readline().decode("utf-8", errors="ignore").strip()

                if not line:
                    continue

                parts = line.split(";")

                if len(parts) != 7:
                    print(f"Invalid data received: {line}")
                    continue

                try:
                    time_ms, x, y, z, angle_time, angle, trigger = map(float, parts)

                    print(
                        f"Time: {time_ms:.2f}, "
                        f"X: {x:.2f}, Y: {y:.2f}, Z: {z:.2f}, "
                        f"Angle Time: {angle_time:.2f}, "
                        f"Angle: {angle:.2f}, "
                        f"Trigger: {trigger:.0f}"
                    )

                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    save_to_csv(
                        [timestamp, time_ms, x, y, z, angle_time, angle, trigger],
                        RAW_OUTPUT_FILE,
                        RAW_HEADERS
                    )

                    if trigger == 1:
                        process_angle_data(angle_time, angle)

                except ValueError:
                    print(f"Data conversion error: {line}")

    except serial.SerialException as e:
        print(f"Serial port access error: {e}")


# =====================================================
# =============== LINEAR REGRESSION ===================
# =====================================================

def calculate_linear_regression(time_data, theta_mean_data):
    """
    Performs linear regression of angle vs time.
    Returns slope (degrees/hour) and intercept.
    """

    # Convert time from milliseconds to hours
    time_hours = np.array(time_data) / 3600000

    coefficients = np.polyfit(time_hours, theta_mean_data, 1)

    slope = coefficients[0]      # degrees/hour
    intercept = coefficients[1]

    return slope, intercept


# =====================================================
# =============== PLOT CONFIGURATION ==================
# =====================================================

fig, ax = plt.subplots(figsize=(8, 5))

line_mean, = ax.plot([], [], 'b-', label=r'$\theta_m$ (Moving Average)')

ax.set_xlabel("Time (hours)")
ax.set_ylabel("Oscillation plane angle (°)")
ax.set_title("Moving Average and Standard Deviation of $\\theta$")

info_text = ax.text(
    0.05, 0.95, '',
    transform=ax.transAxes,
    fontsize=10,
    verticalalignment='top',
    bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5)
)


# =====================================================
# =============== PLOT UPDATE FUNCTION =================
# =====================================================

def update_plot(frame):

    with data_lock:

        if not time_data or not theta_mean_data:
            return line_mean, info_text

        time_hours = np.array(time_data) / 3600000

        line_mean.set_data(time_hours, theta_mean_data)

        # Remove previous shaded regions
        for collection in ax.collections:
            collection.remove()

        ax.fill_between(
            time_hours,
            np.array(theta_mean_data) - np.array(theta_std_data),
            np.array(theta_mean_data) + np.array(theta_std_data),
            alpha=0.2
        )

        slope, intercept = calculate_linear_regression(
            time_data, theta_mean_data
        )

        patch = Patch(alpha=0.2, label=r'$\sigma_\theta$ (Standard Deviation)')

        ax.legend(
            handles=[line_mean, patch],
            labels=[r'$\theta_m$ (Moving Average)',
                    r'$\sigma_\theta$ (Standard Deviation)'],
            handler_map={str: LegendTitle({'fontsize': 12})},
            loc='upper right'
        )

        ax.set_xlim(min(time_hours), max(time_hours))
        ax.set_ylim(min(theta_mean_data) - 5,
                    max(theta_mean_data) + 5)

        last_measurement_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        info_text.set_text(
            f"Last measurement: {last_measurement_time}\n"
            f"θ: {angle_samples[-1]:.2f}°\n"
            f"θ_m: {theta_mean_data[-1]:.2f}°\n"
            f"Standard Deviation: {theta_std_data[-1]:.2f}°\n"
            f"Precession speed: {slope:.3f}°/h"
        )

    return line_mean, info_text


# =====================================================
# ===================== MAIN ==========================
# =====================================================

if __name__ == "__main__":

    serial_thread = threading.Thread(
        target=read_serial,
        daemon=True
    )

    serial_thread.start()

    animation = FuncAnimation(
        fig,
        update_plot,
        interval=1000,
        blit=False
    )

    plt.show()
