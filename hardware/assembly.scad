// FerrumFS demo assembly: TX pod on top of a wooden desk, RX pod glued
// underneath, dipole field lines threading the wood. Render-only.

use <tx_coil_mount.scad>
use <rx_sensor_pod.scad>

table_t = 20;      // desk thickness, mm
show_field = true;

// desk slice
// desk, cut away at y=0 so the lines are visible going through it
color("BurlyWood") translate([-90, 1.5, -table_t]) cube([180, 60, table_t]);

// TX on top: pod + copper winding + iron core
translate([0, 0, 0]) {
    color("DimGray") tx_pod();
    color("Chocolate") translate([0, 0, 0.8]) difference() {
        cylinder(d = 24, h = 32, $fn = 64);
        translate([0, 0, -1]) cylinder(d = 8.6, h = 40, $fn = 32);
    }
    color("Silver") translate([0, 0, 0]) cylinder(d = 8, h = 44, $fn = 32);
    color("Silver") translate([0, 0, 44]) cylinder(d = 13, h = 5.3, $fn = 6);  // bolt head
}

// RX underneath, flipped so the sensor faces up at the coil
translate([0, 0, -table_t]) rotate([180, 0, 0]) {
    color("SteelBlue") rx_pod();
    color("Black") translate([-7, -6.5, 0.8]) cube([14, 13, 1.6]);   // GY-271
}

// dipole field lines: r = k * sin^2(theta), centred on the coil
module field_line(k, phi) {
    pts = [for (t = [8:4:172]) let(r = k * pow(sin(t), 2))
        [r * sin(t) * cos(phi), r * sin(t) * sin(phi), 4 + r * cos(t)]];
    for (i = [0:len(pts) - 2])
        hull() { translate(pts[i]) sphere(0.7, $fn = 8); translate(pts[i + 1]) sphere(0.7, $fn = 8); }
}

if (show_field)
    color("DeepSkyBlue", 0.8)
        for (k = [45, 75, 110]) for (phi = [0, 180]) field_line(k, phi);
