import os
from functools import partial
import pyproj
from shapely.ops import transform
from shapely.geometry import Point, Polygon
import geopandas as gpd
import googlemaps
import polyline
import time
import gmplot
import operator
from flask import Flask, render_template, flash, request
from wtforms import Form, TextField, TextAreaField, validators, StringField, SubmitField

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(32)

proj_wgs84 = pyproj.Proj(init='epsg:4326')


def geodesic_point_buffer(lat, lon, km):
    # Azimuthal equidistant projection
    aeqd_proj = '+proj=aeqd +lat_0={lat} +lon_0={lon} +x_0=0 +y_0=0'
    project = partial(
        pyproj.transform,
        pyproj.Proj(aeqd_proj.format(lat=lat, lon=lon)),
        proj_wgs84)
    buf = Point(0, 0).buffer(km * 1000)  # distance in metres
    return transform(project, buf).exterior.coords[:]

print('reading file')
start = time.time()
shapefile = gpd.read_file('VegCover_MMB_GSR_2016.shp').to_crs(epsg=4326)
shapes = shapefile[['PerAnyVeg', 'geometry']]

heatshapefile = gpd.read_file('HVI_SA1_SUA_2016.shp').to_crs(epsg=4326)
# get the heat volunability index
heatshapes = heatshapefile[['HVI', 'geometry']]

print(time.time() - start)


@app.route("/", methods=['GET', 'POST'])
def search():
    form = InputForm(request.form)

    if request.method == 'POST' and form.validate():
        start = request.form['start']
        destination = request.form['destination']

        gmaps = googlemaps.Client(key='AIzaSyDVfZ9WzzPwKfQ3nudY6kELVgkaCK0cmJ4')
        directions_result = gmaps.directions(start,
                                             destination,
                                             mode="walking", alternatives=True)
        # results = directions_result[0]

        start = time.time()
        checked_points = set()
        checked_heat_points = set()
        print('finding shapes')
        print(len(directions_result))
        all_points = []
        counts = []
        counts_heat = []

        for route in directions_result:
            encoded_points = route['overview_polyline']['points']
            points = polyline.decode(encoded_points)
            all_points.append(points)
            extended_points = []

            for point in points:
                extended_points.append(tuple(geodesic_point_buffer(point[0], point[1], 20.0)))

            count = 0
            count_heat = 0
            for _, row in shapes.iterrows():
                for point in extended_points:
                    if point in checked_points:
                        continue

                    polygon = Polygon(point)
                    if row.geometry.intersects(polygon):
                        count += row.PerAnyVeg
                        checked_points.add(point)

            for _, row in heatshapes.iterrows():
                for point in extended_points:
                    if point in checked_heat_points:
                        continue

                    polygon = Polygon(point)
                    if row.geometry.intersects(polygon):
                        count_heat += row.HVI  # the higher the worse
                        checked_heat_points.add(point)

            counts.append(count)
            counts_heat.append(count_heat)

            print(time.time() - start)

            print(count)
            print(count_heat)

        # gmplot
        # Latitude and Longitude

        gmap = gmplot.GoogleMapPlotter(-33.877620, 151.204485, 15)

        # find the largest green
        index, value = max(enumerate(counts), key=operator.itemgetter(1))

        # find the lowest heat
        indexH, valueH = max(enumerate(counts_heat), key=operator.itemgetter(1))

        for i, p in enumerate(all_points):

            if i == index:
                continue

            else:
                lats, lons = zip(*p)
                # polygon
                gmap.plot(lats, lons, 'silver', edge_width=10)

                marker = p[int(len(p) / 2)]
                # percent = int(counts[i]/sum(counts))
                gmap.marker(marker[0], marker[1], title='{0:.2f} {1}'.format(counts[i], counts_heat[i]),
                            label='{0:.2f} HVI={1}'.format(counts[i], counts_heat[i]))

        lats, lons = zip(*all_points[index])
        # polygon
        gmap.plot(lats, lons, 'cornflowerblue', edge_width=10)

        marker = all_points[index][int(len(all_points[index]) / 2)]
        # percent = int(counts[i]/sum(counts))
        gmap.marker(marker[0], marker[1], title='{0:.2f} {1}'.format(counts[index], counts_heat[index]),
                    label='{0:.2f} HVI={1}'.format(counts[index], counts_heat[index]))

        # gmap.polygon(lats,lons, color = 'cornflowerblue')
        gmap.apikey = "AIzaSyDVfZ9WzzPwKfQ3nudY6kELVgkaCK0cmJ4"
        gmap.draw("templates/map_test.html")

        return render_template('map_test.html')

    return render_template('google.html', form=form)


class InputForm(Form):
    start = StringField('Name:', validators=[validators.required()])
    destination = StringField('Name:', validators=[validators.required()])
    submit = SubmitField('Search')


if __name__ == '__main__':
    app.run()
