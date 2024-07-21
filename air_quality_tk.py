import numpy as np
import paho.mqtt.client as mqtt
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque
import json
import os.path
import sqlite3
from cycler import cycler
import matplotlib as mpl
mpl.rcParams['axes.prop_cycle'] = cycler(color='bgrcmyk')
import matplotlib.ticker as ticker
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import tkinter as tk
from tkinter import ttk

TIMEZONE = np.timedelta64(-4, 'h')
### levels
GOOD = 'Good'
FAIR = 'Fair'
MODERATE = 'Moderate'
POOR = 'Poor'
VERY_POOR = 'Very Poor'
EXTREMELY_POOR = 'Extremely Poor'
levelColors = {GOOD:('b',.1),
               FAIR:('g',.1),
               MODERATE:('y',.1),
               POOR:('tab:orange',.1),
               VERY_POOR:('r',.1),
               EXTREMELY_POOR:('r',.3)
               }
               
AirQualityLevels = {
    'pm25':[[ 0, GOOD],
            [10, FAIR],
            [20, MODERATE],
            [25, POOR],
            [50, VERY_POOR],
            [75, EXTREMELY_POOR]],
#    'pm10':[[ 0, GOOD],
#            [20, FAIR],
#            [40, MODERATE],
#            [50, POOR],
#            [100, VERY_POOR],
#            [150, EXTREMELY_POOR]],
    'co2':[[  0, GOOD],
           [ 500, FAIR],
           [ 800, MODERATE],
           [1000, POOR],
           [1200, VERY_POOR],
           [1800, EXTREMELY_POOR]],
#    'nox':[[  0, GOOD],
#           [ 20, FAIR],
#           [100, MODERATE],
#           [200, POOR],
#           [300, VERY_POOR],
#           [400, EXTREMELY_POOR]],
#    'voc':[[  0, GOOD],
#           [150, FAIR],
#           [200, MODERATE],
#           [250, POOR],
#           [300, VERY_POOR],
#           [400, EXTREMELY_POOR]]
}
def getLevel(name, value):
    if name in AirQualityLevels:
        for v, level in AirQualityLevels[name][::-1]:
            #print(f'    {name}:{value} -- {v} {level}')
            if v <= value:
                out = level
                break
    else:
        out = None
    return out
                
HOME = os.path.split(os.path.abspath('air_quality_tk.py'))[0]
DB_FILE = os.path.join(HOME, 'air_quality_2.db')
sql = '''\
CREATE TABLE IF NOT EXISTS AirQuality 
    (measurement_time DATETIME UNIQUE,
     temperature FLOAT,
     pressure FLOAT,
     humidity FLOAT,
     co2 FLOAT,
     nox FLOAT,
     voc FLOAT,
     aqi_voc,
     aqi_nox,
     pm1 FLOAT,
     pm10 FLOAT,
     pm25 FLOAT,
     lux FLOAT)
'''
db = sqlite3.connect(DB_FILE)
db.execute(sql)

# MQTT settings
# MQTT_BROKER = "mqtt.eclipseprojects.io"
MQTT_BROKER = "192.168.86.177"

MQTT_PORT = 1883
MQTT_TOPIC = "airquality/airquality_3_A4BB24/state"

# Data storage
MAXLEN = 1440 * 2 + 60
line_data = deque(maxlen=MAXLEN)

columns = [['measurement_time', None],
           [     'temperature', 0],
           [        'pressure', 1],
           [        'humidity', 2],
           [             'co2', 3],
           [             'lux', 4],
           [             'nox', 5],
           [             'voc', 6],
           [         'aqi_voc', 7],
           [         'aqi_nox', 8],
           [             'pm1', 9],
           [            'pm10', 9],
           [            'pm25', 9],
           ]
#columns = 'datetime temperature pressure humidity co2 nox voc aqi_voc aqi_nox pm1 pm10 pm25 lux'.split()
cols = ','.join([c[0] for c in columns])

def insert(line):
    db = sqlite3.connect(DB_FILE)
    values = f'("{line[0]:s}",{",".join(map(str, line[1:]))})'
    sql = f'''\
INSERT INTO AirQuality 
VALUES {values}
'''
    try:
        db.execute(sql)
        db.commit()
    except sqlite3.IntegrityError:
        pass
    sql = f'''\
SELECT count(*) 
FROM AirQuality 
WHERE measurement_time == "{line[0]}"
'''
    c = db.execute(sql)
    count = c.fetchone()[0]
    assert count == 1

if os.path.exists(DB_FILE):
    db = sqlite3.connect(DB_FILE)
    c = db.execute(f'''\
SELECT {cols} 
FROM AirQuality 
ORDER BY measurement_time DESC
LIMIT {MAXLEN}
''')
    lines = c.fetchall()[::-1]
    lines = [[np.datetime64(l[0], 'm')] + list(l[1:]) for l in lines]
    line_data.extend(lines)


def thousands_formatter(x, pos):
    if x >= 1_000_000:
        return f'{x*1e-6:.1f}M'
    elif x >= 1_000:
        return f'{x*1e-3:.1f}K'
    else:
        return f'{x:.1f}'
    
# MQTT on_message callback
##      #units, default range
axes = [('$^\circ$F', (60, 80)), # 0
        ('KPa', (99, 102)),      # 1
        ('%', (35, 45)),         # 2
        ('PPM', (300, 1500)),    # 3
        (' - ', (0, 1000)),      # 4
        (' . ', (16000, 17000)), # 5
        (' . ', (30000, 32000)), # 6
        (' . ', (0, 200)),       # 7
        (' . ', (0, 10)),        # 8
        (' . ', (0, 10)),        # 9
        ]
def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode('utf-8')
        data = json.loads(payload)
        # Assuming data has fields 'timestamp' and 'air_quality'
        timestamp = np.datetime64("now", 's')
        
        line = [timestamp] + [data[c[0]] for c in columns[1:]]
        line[1] = line[1] * 9/5 + 32
        line[2] /= 1000.
        line_data.append(line)
        #print(','.join(map(str, line)))
        #insert(line) ## handled by air_quality_logger.py
        
    except Exception as e:
        print(f"Error processing message: {e}")
        raise
# MQTT client setup
client = mqtt.Client()
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.subscribe(MQTT_TOPIC)
client.loop_start()

# Plotting setup
def create_figure(num_axes, figsize, sharex, dpi=150):
    fig = plt.figure(figsize=figsize, dpi=dpi)
    axes = []
    for i in range(num_axes):
        if sharex == True:
            if i == 0:
                ax = fig.add_subplot(num_axes, 1, i + 1)
            else:
                ax = fig.add_subplot(num_axes, 1, i + 1, sharex=axes[0])
        elif sharex:
                ax = fig.add_subplot(num_axes, 1, i + 1, sharex=sharex)
        else:
            ax = fig.add_subplot(num_axes, 1, i + 1)
        axes.append(ax)
    axes[-1].set_xlabel('Time')
    return fig, axes

def create_tab(notebook, num_axes, figsize, sharex, dpi=150, name='Tab'):
    # Create the first tab
    tab = ttk.Frame(notebook)
    notebook.add(tab, text=name)

    # Create the first figure and add it to the first tab
    fig, ax = create_figure(num_axes, figsize, sharex, dpi)
    canvas = FigureCanvasTkAgg(fig, master=tab)  # A tk.DrawingArea.
    canvas.draw()
    canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

    # Add the navigation toolbar for the first tab
    toolbar = NavigationToolbar2Tk(canvas, tab)
    toolbar.update()
    canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)
    return fig, ax
    
#fig, ax = plt.subplots(7, clear=True, num=1, figsize=(14, 10), sharex=True); ax = ax.ravel()
root = tk.Tk()
root.title("MQTT Air Quality Monitor")
# Create a style and configure the tab font size
style = ttk.Style()
style.configure('TNotebook.Tab', font=('Helvetica', 18, 'bold'))

notebook = ttk.Notebook(root)
notebook.pack(expand=1, fill='both')

fig1, ax1 = create_tab(notebook, 4, figsize=(14, 10), sharex=True, name='Temp/Pressure/Humitity/Co2')
fig2, ax2 = create_tab(notebook, 4, figsize=(14, 10), sharex=ax1[0], name='Lux/NoX/Voc/AQI_voc')
fig3, ax3 = create_tab(notebook, 2, figsize=(14, 10), sharex=ax1[0], name='AQI_NoX/PM')

ax = ax1 + ax2 + ax3
lines = []
texts = []
points = []
areas = []
i = 0
for column in columns[1:]:
    axi = column[1]
    _ax = ax[axi]
    line = _ax.plot([], [], '-', label=column[0])[0]
    lines.append(line)
    point = _ax.plot([], [], 'o')[0]
    points.append(point)
    texts.append(_ax.text(0, 0, '', ha='left', fontsize=8))
    eons = [np.datetime64("2000-01-01"),
            np.datetime64("2000-01-01"),
            np.datetime64("2200-01-01"),
            np.datetime64("2200-01-01")]
    if column[0] in AirQualityLevels:
        last_value = 0
        last_color = 'b'
        last_alpha = .1
        for value, level in AirQualityLevels[column[0]][1:]:
            color, alpha = levelColors[level]
            areas.append(_ax.fill(eons,
                                  [last_value, value, value, last_value],
                                  color=last_color, alpha=last_alpha)[0])
            last_value = value
            last_color = color
            last_alpha = alpha
        areas.append(_ax.fill(eons,
                              [last_value, 1e6, 1e6, last_value],
                              color=last_color, alpha=last_alpha)[0])

for i, (units, rng) in enumerate(axes):
    ax[i].set_ylabel(units)
    ax[i].set_ylim(rng)
    ax[i].legend(ncol=3)
    ax[i].yaxis.set_major_formatter(ticker.FuncFormatter(thousands_formatter))

fig1.tight_layout()
fig2.tight_layout()
def init():
    return lines + texts + points + areas

last_time = [np.datetime64("2000-01-01")]
def update(frame):
    if last_time[0] >= line_data[-1][0]:
        return lines + texts + points + areas
    last_time[0] = line_data[-1][0]
    if len(line_data) > 0:
        x = [l[0] + TIMEZONE for l in line_data]
        rngs = [[np.inf, -np.inf] for _ax in ax]
        for i, column in enumerate(columns[1:]):
            axi = column[1]
            _ax = ax[axi]
            y = [l[i+1] for l in line_data]
            level = getLevel(column[0], y[-1])
            yvals = [_y for _y in y if _y is not None]
            if np.min(yvals) <= rngs[axi][0]:
                rngs[axi][0] = np.min(yvals)
            if np.max(yvals) > rngs[axi][1]:
                rngs[axi][1] = np.max(yvals)
            #ymin = np.min([np.min(yvals), preset_rng[0]])
            #ymax = np.max([np.max(yvals), preset_rng[1]])
            lines[i].set_data(x, y)
            points[i].set_data([x[-1]], [y[-1]])
            if level:
                points[i].set_color(levelColors[level][0])
            else:
                points[i].set_color(lines[i].get_color())
            if i == 1:
                texts[i].set_text(f' {y[-1]:.1f}')
            else:
                texts[i].set_text(f' {y[-1]:.0f}')
            texts[i].set_x(x[-1])
            texts[i].set_y(y[-1])

        for rng, _ax in zip(rngs, ax):
            xtra = (rng[1] - rng[0]) * .1
            rng[0] -= xtra
            rng[1] += xtra
            if not np.any(np.isinf(rng)):
                _ax.set_ylim(rng)
                
        ax[0].set_xlim(x[0] - np.timedelta64(1, 'm'), x[-1] + np.timedelta64(2, 'h'))
        now = np.datetime64("now", 'h')
        xt = np.arange(now - np.timedelta64(24, 'h'),
                       now + np.timedelta64(1, 'm'),
                       np.timedelta64(3, 'h')).astype('datetime64[m]')
        labels = [str(t).split('T')[1] for t in xt]
        ## minutes days since 1970-01-01
        ax[-1].set_xticks(xt, labels)
        ax[-1].set_xlim(xt[0] - np.timedelta64(30, 'm'), x[-1] + np.timedelta64(60, 'm'))
        fig1.tight_layout()
        fig1.canvas.draw()
        fig2.tight_layout()
        fig2.canvas.draw()
    return lines + texts + points + areas

ani = animation.FuncAnimation(fig1, update, init_func=init, blit=True, interval=500)
ani = animation.FuncAnimation(fig2, update, init_func=init, blit=True, interval=600)
#plt.show()


# Ensure the script runs indefinitely to keep receiving MQTT messages
try:
    root.mainloop()
except KeyboardInterrupt:
    pass
finally:
    client.loop_stop()
    client.disconnect()
    print("Disconnected from MQTT broker.")
