#!/usr/bin/env python3
"""
Test script to retrieve information from Vaillant boiler using myPyllant library (v0.9.9)
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from myPyllant.api import MyPyllantAPI
from myPyllant.const import ALL_COUNTRIES, BRANDS, DEFAULT_BRAND

logging.basicConfig(level=logging.INFO)

async def get_boiler_info(username, password, brand="vaillant", country="poland"):
    """
    Retrieve comprehensive information from your Vaillant boiler
    """
    print(f"\nConnecting to myVaillant API (brand: {brand}, country: {country})...")
    
    try:
        async with MyPyllantAPI(username, password, brand, country) as api:
            print("Login successful!\n")

            # Get homes
            print("=" * 60)
            print("HOMES")
            print("=" * 60)
            async for home in api.get_homes():
                print(f"  Home Name:      {home.home_name}")
                print(f"  Nomenclature:   {home.nomenclature}")
                print(f"  Serial Number:  {home.serial_number}")
                print(f"  System ID:      {home.system_id}")
                print(f"  Country Code:   {home.country_code}")
                print(f"  Timezone:       {home.timezone}")
                print(f"  State:          {home.state}")
                print(f"  Firmware:       {home.firmware_version}")
                print(f"  Address:        {home.address}")
                print()

            # Get all systems with full details
            print("=" * 60)
            print("SYSTEMS")
            print("=" * 60)
            async for system in api.get_systems(
                include_connection_status=True,
                include_diagnostic_trouble_codes=True,
                include_rts=True,
                include_mpc=True,
            ):
                print(f"\n  System ID:            {system.id}")
                print(f"  System Name:          {system.system_name}")
                print(f"  Brand:                {system.brand_name}")
                print(f"  Control Identifier:   {system.control_identifier}")
                print(f"  Connected:            {system.connected}")
                print(f"  Timezone:             {system.timezone}")

                # System-level temperatures & pressures
                print(f"\n  --- SYSTEM READINGS ---")
                print(f"  Outdoor Temperature:          {system.outdoor_temperature}°C")
                print(f"  Outdoor Temp Avg 24h:         {system.outdoor_temperature_average_24h}°C")
                print(f"  Water Pressure:               {system.water_pressure} bar")
                print(f"  System Flow Temperature:      {system.system_flow_temperature}°C")
                print(f"  Cylinder Temp Top DHW:        {system.cylinder_temperature_sensor_top_dhw}°C")
                print(f"  Cylinder Temp Bottom DHW:     {system.cylinder_temperature_sensor_bottom_dhw}°C")
                print(f"  Cylinder Temp Top CH:         {system.cylinder_temperature_sensor_top_ch}°C")
                print(f"  Cylinder Temp Bottom CH:      {system.cylinder_temperature_sensor_bottom_ch}°C")
                print(f"  Energy Manager State:         {system.energy_manager_state}")

                # Zones
                print(f"\n  --- ZONES ({len(system.zones)}) ---")
                for zone in system.zones:
                    print(f"\n  Zone [{zone.index}]: {zone.name}")
                    print(f"    Active:                     {zone.is_active}")
                    print(f"    Heating State:              {zone.heating_state}")
                    print(f"    Current Room Temperature:   {zone.current_room_temperature}°C")
                    print(f"    Current Room Humidity:       {zone.current_room_humidity}%")
                    print(f"    Desired Temp Setpoint:      {zone.desired_room_temperature_setpoint}°C")
                    print(f"    Desired Temp Heating:       {zone.desired_room_temperature_setpoint_heating}°C")
                    print(f"    Desired Temp Cooling:       {zone.desired_room_temperature_setpoint_cooling}°C")
                    print(f"    Operation Mode Heating:     {zone.heating.operation_mode_heating}")
                    print(f"    Set Back Temperature:       {zone.heating.set_back_temperature}°C")
                    print(f"    Manual Mode Setpoint:       {zone.heating.manual_mode_setpoint_heating}°C")
                    print(f"    Current Special Function:   {zone.current_special_function}")
                    print(f"    Quick Veto Ongoing:         {zone.quick_veto_ongoing}")
                    print(f"    Holiday Planned:            {zone.general.holiday_planned}")
                    print(f"    Holiday Ongoing:            {zone.general.holiday_ongoing}")
                    print(f"    Cooling Allowed:            {zone.is_cooling_allowed_circuit}")
                    if zone.heating.time_program_heating:
                        print(f"    Time Program:               (set)")
                    if zone.associated_circuit:
                        print(f"    Associated Circuit Index:   {zone.associated_circuit_index}")

                # Circuits
                print(f"\n  --- CIRCUITS ({len(system.circuits)}) ---")
                for circuit in system.circuits:
                    print(f"\n  Circuit [{circuit.index}]:")
                    print(f"    Circuit State:              {circuit.circuit_state}")
                    print(f"    Flow Temperature:           {circuit.current_circuit_flow_temperature}°C")
                    print(f"    Heating Curve:              {circuit.heating_curve}")
                    print(f"    Min Flow Temp Setpoint:     {circuit.heating_flow_temperature_minimum_setpoint}°C")
                    print(f"    Max Flow Temp Setpoint:     {circuit.heating_flow_temperature_maximum_setpoint}°C")
                    print(f"    Cooling Allowed:            {circuit.is_cooling_allowed}")

                # Domestic Hot Water
                if system.domestic_hot_water:
                    print(f"\n  --- DOMESTIC HOT WATER ({len(system.domestic_hot_water)}) ---")
                    for dhw in system.domestic_hot_water:
                        print(f"\n  DHW [{dhw.index}]:")
                        print(f"    Current DHW Temperature:    {dhw.current_dhw_temperature}°C")
                        print(f"    Tapping Setpoint:           {dhw.tapping_setpoint}°C")
                        print(f"    Min Setpoint:               {dhw.min_setpoint}°C")
                        print(f"    Max Setpoint:               {dhw.max_setpoint}°C")
                        print(f"    Operation Mode:             {dhw.operation_mode_dhw}")
                        print(f"    Special Function:           {dhw.current_special_function}")
                        print(f"    Cylinder Boosting:          {dhw.is_cylinder_boosting}")

                # Devices (heat generators, etc.)
                print(f"\n  --- DEVICES ({len(system.devices)}) ---")
                for device in system.devices:
                    print(f"\n  Device: {device.name_display}")
                    print(f"    Type:                       {device.type}")
                    print(f"    Device Type:                {device.device_type}")
                    print(f"    Product Name:               {device.product_name_display}")
                    print(f"    Brand:                      {device.brand_name}")
                    print(f"    Serial Number:              {device.device_serial_number}")
                    print(f"    Article Number:             {device.article_number}")
                    print(f"    eBus ID:                    {device.ebus_id}")
                    print(f"    First Data:                 {device.first_data}")
                    print(f"    Last Data:                  {device.last_data}")
                    print(f"    On/Off Cycles:              {device.on_off_cycles}")
                    print(f"    Operation Time:             {device.operation_time}")
                    print(f"    Current Power:              {device.current_power}")
                    if device.operational_data:
                        print(f"    Operational Data:           {json.dumps(device.operational_data, indent=6, default=str)}")
                    if device.diagnostic_trouble_codes:
                        print(f"    Diagnostic Trouble Codes:   {device.diagnostic_trouble_codes}")
                    if device.properties:
                        print(f"    Properties:                 {device.properties}")

                # Primary heat generator shortcut
                phg = system.primary_heat_generator
                if phg:
                    print(f"\n  --- PRIMARY HEAT GENERATOR ---")
                    print(f"    Name:           {phg.name_display}")
                    print(f"    Product:        {phg.product_name_display}")
                    print(f"    Serial:         {phg.device_serial_number}")
                    print(f"    Current Power:  {phg.current_power}")

                # Ventilation
                if system.ventilation:
                    print(f"\n  --- VENTILATION ({len(system.ventilation)}) ---")
                    for vent in system.ventilation:
                        print(f"    Operation Mode:     {vent.operation_mode_ventilation}")
                        print(f"    Max Day Fan Stage:  {vent.maximum_day_fan_stage}")
                        print(f"    Max Night Fan Stage:{vent.maximum_night_fan_stage}")

                # Diagnostic trouble codes
                if system.has_diagnostic_trouble_codes:
                    print(f"\n  --- DIAGNOSTIC TROUBLE CODES ---")
                    for dtc in system.diagnostic_trouble_codes:
                        print(f"    {dtc}")

                # Raw state/configuration (for debugging)
                print(f"\n  --- RAW STATE KEYS ---")
                print(f"    State keys:         {list(system.state.keys())}")
                print(f"    Configuration keys: {list(system.configuration.keys())}")
                if system.state.get('system'):
                    print(f"    System state keys:  {list(system.state['system'].keys())}")

                print("\n" + "=" * 60)

    except Exception as e:
        import traceback
        print(f"\nError: {e}")
        traceback.print_exc()
        print("\nPlease check your credentials and brand/country settings.")

if __name__ == "__main__":
    username = input("Enter your myVaillant username (email): ")
    password = input("Enter your myVaillant password: ")

    print(f"\nAvailable brands: {', '.join(BRANDS.keys())}")
    brand = input(f"Enter brand [{DEFAULT_BRAND}]: ") or DEFAULT_BRAND

    print(f"\nAvailable countries for {brand}: {', '.join(ALL_COUNTRIES.keys())}")
    country = input("Enter country [poland]: ") or "poland"

    asyncio.run(get_boiler_info(username, password, brand, country))
