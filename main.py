from flask import Flask, request, jsonify, render_template
import math
from geographiclib.geodesic import Geodesic
import subprocess
import shlex
import os

app = Flask(__name__)
geo_tool = Geodesic.WGS84
csv_file = "coordinates_data.csv"
gps_sdr_sim_path = "gps-sdr-sim.exe"


def calculate_distance_and_azimuth(lat1, lon1, lat2, lon2):
    result = geo_tool.Inverse(lat1, lon1, lat2, lon2)
    return result['s12'], result['azi1']


def calculate_intermediate_points(lat1, lon1, lat2, lon2, speed_kmh, interval=0.1):
    line = geo_tool.InverseLine(lat1, lon1, lat2, lon2)
    total_distance = line.s13
    speed = speed_kmh / 3.6  # Convert speed from km/h to m/s
    num_intervals = math.ceil(total_distance / (speed * interval))
    step_distance = total_distance / num_intervals
    points = []
    for i in range(num_intervals + 1):
        position = line.Position(step_distance * i, Geodesic.STANDARD | Geodesic.LONG_UNROLL)
        points.append({
            'lat': position['lat2'],
            'lng': position['lon2'],
            'azimuth': position['azi2']
        })
    return points


def write_coordinates_to_csv(coords, speed_kmh=180, interval=1):
    with open(csv_file, "w") as file:
        for idx, coord in enumerate(coords):
            time = idx * interval
            file.write(f"{time:.1f}, {coord['lat']:.6f}, {coord['lng']:.6f}, 100.000\n")


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/compute', methods=['POST'])
def compute_coordinates():
    try:
        request_data = request.get_json()
        if not request_data:
            return jsonify({'error': 'Пустой запрос. Проверьте данные.'}), 400
        coords = request_data.get('coords')
        speed = request_data.get('speed', 180)  # Default speed is 180 km/h
        interval = request_data.get('interval', 1)  # Default interval is 1 second
        if not isinstance(coords, list) or len(coords) < 2 or any(not isinstance(coord, dict) or 'lat' not in coord or 'lng' not in coord for coord in coords):
            return jsonify({'error': 'Неверный формат координат или недостаточное количество точек.'}), 400
        lat_start, lon_start = float(coords[0]['lat']), float(coords[0]['lng'])
        lat_end, lon_end = float(coords[-1]['lat']), float(coords[-1]['lng'])
        distance, azimuth = calculate_distance_and_azimuth(lat_start, lon_start, lat_end, lon_end)
        intermediate_points = calculate_intermediate_points(lat_start, lon_start, lat_end, lon_end, speed_kmh=speed, interval=interval)
        write_coordinates_to_csv(intermediate_points, speed_kmh=speed, interval=interval)
        response_data = {
            'distance': distance,
            'azimuth': azimuth,
            'intermediate_points': intermediate_points
        }
        return jsonify(response_data), 200
    except ValueError as ve:
        return jsonify({'error': f'Ошибка в данных: {str(ve)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Ошибка: {str(e)}'}), 400


@app.route('/send_simulation', methods=['POST'])
def send_simulation():
    try:
        if not os.path.exists(csv_file):
            return jsonify({'error': 'CSV файл с координатами не найден.'}), 400
        print('Trying to send data to gps-sdr-sim...')
        command = f"{gps_sdr_sim_path} -e brdc1470.24n -b 8 -x {csv_file}"
        print(f"Executing command: {command}")
        if not os.path.exists(gps_sdr_sim_path):
            print(f"Ошибка: файл {gps_sdr_sim_path} не найден.")
            return jsonify({'error': f'Ошибка: файл {gps_sdr_sim_path} не найден.'}), 500
        proc = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        print(f"Command output: {stdout.decode('utf-8')}")
        if proc.returncode != 0:
            print(f"Command error: {stderr.decode('utf-8')}")
            return jsonify({'error': f"Ошибка выполнения команды: {stderr.decode('utf-8')}"}), 500
        return jsonify({'status': 'Simulation sent'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/send_hackrf', methods=['POST'])
def send_hackrf():
    try:
        if not os.path.exists("gpssim.bin"):
            return jsonify({'error': 'Файл gpssim.bin не найден.'}), 400
        print('Trying to send data to HackRF...')
        command = "hackrf_transfer.exe -t ./gpssim.bin -f 1575420000 -s 2600000 -a 1 -x 0"
        print(f"Executing command: {command}")
        proc = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        print(f"Command output: {stdout.decode('utf-8')}")
        if proc.returncode != 0:
            print(f"Command error: {stderr.decode('utf-8')}")
            return jsonify({'error': f"Ошибка выполнения команды: {stderr.decode('utf-8')}"}), 500
        return jsonify({'status': 'HackRF data sent'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8000, debug=True)