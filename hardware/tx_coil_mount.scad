// FerrumFS TX pod: holds the coil vertically with its core flush to the
// bottom face, so the field goes straight down through the table.

core_d    = 8.4;   // M8 iron bolt / ferrite rod + clearance
coil_od   = 24;    // wound coil outer diameter
coil_h    = 32;    // winding length
floor_t   = 0.8;   // thin floor: every mm costs field strength (~1/r^3)
wall      = 2;
pcb_w     = 20;    // MOSFET + flyback diode perfboard
pcb_l     = 30;
cable_d   = 5;
$fn = 96;

od = coil_od + 2 * wall;
h  = coil_h + floor_t + 4;

module tx_pod() difference() {
    union() {
        cylinder(d = od, h = h);
        translate([od / 2 - wall, -pcb_w / 2 - wall, 0])
            cube([pcb_l + 2 * wall, pcb_w + 2 * wall, h * 0.6]);   // driver bay
    }
    translate([0, 0, floor_t]) cylinder(d = coil_od + 0.6, h = h);  // coil
    translate([0, 0, -1]) cylinder(d = core_d, h = h + 2);           // core pokes through
    translate([od / 2, -pcb_w / 2, floor_t])
        cube([pcb_l, pcb_w, h]);                                     // pcb pocket
    translate([0, 0, h * 0.4]) rotate([0, 90, 0])
        cylinder(d = cable_d, h = od + pcb_l + 10);                  // leads + cable
}

tx_pod();
