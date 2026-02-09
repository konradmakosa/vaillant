#!/usr/bin/env python3
"""
Export comprehensive data from Vaillant boiler to JSON files
"""
import asyncio
import json
import sys
from datetime import datetime, timedelta
from myPyllant.api import MyPyllantAPI

async def export_system_data(username, password, brand="vaillant", country="germany", include_historical=False):
    """
    Export system data to JSON files
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        async with MyPyllantAPI(username, password, brand, country) as api:
            # Export basic system information
            systems_data = []
            async for system in api.get_systems():
                system_dict = {
                    "system_id": system.system_id,
                    "name": system.name,
                    "serial_number": system.serial_number,
                    "timezone": str(system.timezone),
                    "control_identifier": system.control_identifier,
                    "brand": system.brand,
                    "country": system.country,
                    "zones": [],
                    "domestic_hot_water": [],
                    "heat_generator": None,
                    "circuits": []
                }
                
                # Export zones
                for zone in system.zones:
                    zone_data = {
                        "name": zone.name,
                        "current_temperature": zone.current_temperature,
                        "target_temperature": zone.target_temperature,
                        "heating_mode": zone.heating_mode,
                        "active": zone.active,
                        "heating_active": zone.heating_active
                    }
                    if hasattr(zone, 'set_back_temperature'):
                        zone_data["set_back_temperature"] = zone.set_back_temperature
                    system_dict["zones"].append(zone_data)
                
                # Export domestic hot water
                if system.domestic_hot_water:
                    for dhw in system.domestic_hot_water:
                        dhw_data = {
                            "name": dhw.name,
                            "current_temperature": dhw.current_temperature,
                            "target_temperature": dhw.target_temperature,
                            "operation_mode": dhw.operation_mode,
                            "boost_active": dhw.boost_active,
                            "heating_active": dhw.heating_active
                        }
                        system_dict["domestic_hot_water"].append(dhw_data)
                
                # Export heat generator
                if system.heat_generator:
                    hg = system.heat_generator
                    hg_data = {
                        "device_type": hg.device_type,
                        "name": hg.name,
                        "brand": hg.brand,
                        "serial_number": hg.serial_number
                    }
                    if hasattr(hg, 'current_power_consumption'):
                        hg_data["current_power_consumption"] = hg.current_power_consumption
                    if hasattr(hg, 'energy_efficiency_label'):
                        hg_data["energy_efficiency_label"] = hg.energy_efficiency_label
                    system_dict["heat_generator"] = hg_data
                
                # Export circuits
                if system.circuits:
                    for circuit in system.circuits:
                        circuit_data = {
                            "name": circuit.name,
                            "circuit_type": circuit.circuit_type,
                            "heating_active": circuit.heating_active
                        }
                        if hasattr(circuit, 'current_flow_temperature'):
                            circuit_data["current_flow_temperature"] = circuit.current_flow_temperature
                        if hasattr(circuit, 'current_return_temperature'):
                            circuit_data["current_return_temperature"] = circuit.current_return_temperature
                        system_dict["circuits"].append(circuit_data)
                
                systems_data.append(system_dict)
                
                # Export historical data if requested
                if include_historical:
                    print(f"Exporting historical data for system {system.system_id}...")
                    end_time = datetime.now(system.timezone)
                    start_time = end_time - timedelta(days=7)  # Last 7 days
                    
                    try:
                        historical_data = await api.get_data(
                            system, 
                            start_time=start_time, 
                            end_time=end_time
                        )
                        
                        historical_list = []
                        for data_point in historical_data:
                            historical_list.append({
                                "device_name": data_point.device_name,
                                "timestamp": data_point.timestamp.isoformat(),
                                "value": data_point.value,
                                "data_type": data_point.data_type
                            })
                        
                        # Save historical data
                        historical_filename = f"historical_data_{system.system_id}_{timestamp}.json"
                        with open(historical_filename, 'w') as f:
                            json.dump(historical_list, f, indent=2)
                        print(f"Historical data saved to {historical_filename}")
                        
                    except Exception as e:
                        print(f"Could not retrieve historical data: {e}")
            
            # Save basic system data
            filename = f"system_data_{timestamp}.json"
            with open(filename, 'w') as f:
                json.dump(systems_data, f, indent=2)
            
            print(f"System data exported to {filename}")
            return filename
            
    except Exception as e:
        print(f"Error exporting data: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python export_data.py <username> <password> [brand] [country] [--historical]")
        print("Example: python export_data.py user@example.com password vaillant germany --historical")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    brand = sys.argv[3] if len(sys.argv) > 3 else "vaillant"
    country = sys.argv[4] if len(sys.argv) > 4 else "germany"
    include_historical = "--historical" in sys.argv
    
    asyncio.run(export_system_data(username, password, brand, country, include_historical))
