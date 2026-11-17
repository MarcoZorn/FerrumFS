// FerrumFS RX pod: sensor sits face-down on a thin floor, under the table,
// facing the TX coil. Fits a GY-271 (QMC5883L) or an SS49E on a stub board.

sensor_w  = 14.5;  // GY-271 breakout
sensor_l  = 13.5;
sensor_h  = 4;
floor_t   = 0.8;
wall      = 2;
pod_d     = 40;
pod_h     = 14;
cable_d   = 5;
lid_clear = 0.25;
$fn = 96;

module body() {
    difference() {
        cylinder(d = pod_d, h = pod_h);
        translate([0, 0, floor_t]) cylinder(d = pod_d - 2 * wall, h = pod_h);
        translate([0, 0, pod_h - 5]) rotate([0, 90, 0]) cylinder(d = cable_d, h = pod_d);
    }
    // sensor cradle: keeps the chip centred on the coil axis
    difference() {
        translate([-(sensor_w + 2 * wall) / 2, -(sensor_l + 2 * wall) / 2, 0])
            cube([sensor_w + 2 * wall, sensor_l + 2 * wall, floor_t + sensor_h]);
        translate([-sensor_w / 2, -sensor_l / 2, floor_t])
            cube([sensor_w, sensor_l, sensor_h + 1]);
    }
}

module lid() {
    cylinder(d = pod_d, h = 1.6);
    translate([0, 0, 1.6]) difference() {
        cylinder(d = pod_d - 2 * wall - 2 * lid_clear, h = 3);
        cylinder(d = pod_d - 4 * wall, h = 4);
    }
}

body();
translate([pod_d + 6, 0, 0]) lid();
