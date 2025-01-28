// Global variables for charts
let vehicleStatusChart;
let weeklyPerformanceChart;
let dailyStopsChart;
let weeklyOverviewChart;

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initializeSidebar();
    initializeCharts();
    setupEventListeners();
    loadDashboardData();
    
    // Initial data load
    refreshData();
    
    // Set up auto-refresh every 5 minutes
    setInterval(refreshData, 300000);
});

// Sidebar functionality
function initializeSidebar() {
    const sidebarCollapse = document.getElementById('sidebarCollapse');
    const sidebar = document.getElementById('sidebar');
    const content = document.getElementById('content');
    
    sidebarCollapse.addEventListener('click', () => {
        sidebar.classList.toggle('active');
        content.classList.toggle('active');
    });
}

// Initialize all charts
function initializeCharts() {
    // Vehicle Status Chart
    const vehicleStatusCtx = document.getElementById('vehicleStatusChart').getContext('2d');
    vehicleStatusChart = new Chart(vehicleStatusCtx, {
        type: 'doughnut',
        data: {
            labels: ['Free', 'Managed', 'In Repair'],
            datasets: [{
                data: [0, 0, 0],
                backgroundColor: ['#2ecc71', '#3498db', '#e74c3c']
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    });

    // Weekly Performance Chart
    const weeklyPerformanceCtx = document.getElementById('weeklyPerformanceChart').getContext('2d');
    weeklyPerformanceChart = new Chart(weeklyPerformanceCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Performance',
                data: [],
                borderColor: '#3498db',
                fill: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    });

    // Initialize other charts similarly
    initializePointFSCharts();
}

// Initialize Point FS specific charts
function initializePointFSCharts() {
    const dailyStopsCtx = document.getElementById('dailyStopsChart').getContext('2d');
    dailyStopsChart = new Chart(dailyStopsCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Daily Stops',
                data: [],
                backgroundColor: '#3498db'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    });

    const weeklyOverviewCtx = document.getElementById('weeklyOverviewChart').getContext('2d');
    weeklyOverviewChart = new Chart(weeklyOverviewCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Weekly Overview',
                data: [],
                borderColor: '#2ecc71',
                fill: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    });
}

// Set up event listeners
function setupEventListeners() {
    // Navigation
    document.querySelectorAll('[data-section]').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const sectionId = link.getAttribute('data-section');
            showSection(sectionId);
        });
    });

    // Filters
    document.getElementById('vehicleTypeFilter').addEventListener('change', filterVehicles);
    document.getElementById('statusFilter').addEventListener('change', filterVehicles);
}

// Show selected section
function showSection(sectionId) {
    document.querySelectorAll('.section').forEach(section => {
        section.classList.remove('active');
    });
    document.getElementById(`${sectionId}-section`).classList.add('active');
    
    // Update active state in sidebar
    document.querySelectorAll('#sidebar li').forEach(item => {
        item.classList.remove('active');
    });
    document.querySelector(`[data-section="${sectionId}"]`).parentElement.classList.add('active');
}

// Refresh all data
async function refreshData() {
    try {
        await Promise.all([
            loadDashboardData(),
            loadVehiclesData(),
            loadPointFSData()
        ]);
        
        updateLastSyncTime();
    } catch (error) {
        console.error('Error refreshing data:', error);
        showError('Failed to refresh data');
    }
}

// Load dashboard data
async function loadDashboardData() {
    try {
        const response = await fetch('/api/dashboard-data');
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        updateDashboardMetrics(data);
        updateVehicleStatusChart(data.vehicle_status);
        
    } catch (error) {
        console.error('Error loading dashboard data:', error);
        showError('Failed to load dashboard data');
    }
}

// Update dashboard metrics
function updateDashboardMetrics(data) {
    document.getElementById('activeDrivers').textContent = data.active_drivers;
    document.getElementById('totalVehicles').textContent = data.total_vehicles;
    document.getElementById('caSemaine').textContent = `€${data.financial_metrics.ca_semaine}`;
    document.getElementById('caJour').textContent = `€${data.financial_metrics.ca_jour}`;
}

// Update vehicle status chart
function updateVehicleStatusChart(statusData) {
    vehicleStatusChart.data.datasets[0].data = [
        statusData.free,
        statusData.managed,
        statusData.repair
    ];
    vehicleStatusChart.update();
}

// Load vehicles data
async function loadVehiclesData() {
    try {
        const response = await fetch('/api/vehicles');
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        updateVehiclesTable(data.vehicles);
        
    } catch (error) {
        console.error('Error loading vehicles data:', error);
        showError('Failed to load vehicles data');
    }
}

// Update vehicles table
function updateVehiclesTable(vehicles) {
    const tbody = document.querySelector('#vehiclesTable tbody');
    tbody.innerHTML = '';
    
    vehicles.forEach(vehicle => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${vehicle.registration}</td>
            <td>${vehicle.type}</td>
            <td><span class="badge bg-${getStatusColor(vehicle.status)}">${vehicle.status}</span></td>
            <td>${vehicle.driver}</td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="viewVehicleDetails('${vehicle.id}')">
                    <i class='bx bx-detail'></i>
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

// Get status color for badges
function getStatusColor(status) {
    const colors = {
        'free': 'success',
        'managed': 'primary',
        'repair': 'danger'
    };
    return colors[status.toLowerCase()] || 'secondary';
}

// Load Point FS data
async function loadPointFSData() {
    try {
        const response = await fetch('/api/point-fs');
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        updatePointFSCharts(data);
        
    } catch (error) {
        console.error('Error loading Point FS data:', error);
        showError('Failed to load Point FS data');
    }
}

// Update Point FS charts
function updatePointFSCharts(data) {
    // Update daily stops chart
    dailyStopsChart.data.labels = data.daily_stops.map(item => item.date);
    dailyStopsChart.data.datasets[0].data = data.daily_stops.map(item => item.count);
    dailyStopsChart.update();
    
    // Update weekly overview chart
    weeklyOverviewChart.data.labels = data.weekly_overview.map(item => item.week);
    weeklyOverviewChart.data.datasets[0].data = data.weekly_overview.map(item => item.value);
    weeklyOverviewChart.update();
}

// Filter vehicles
function filterVehicles() {
    const typeFilter = document.getElementById('vehicleTypeFilter').value;
    const statusFilter = document.getElementById('statusFilter').value;
    
    // Implementation depends on your data structure
    // This is a placeholder for the filtering logic
}

// Update last sync time
function updateLastSyncTime() {
    const now = new Date();
    document.getElementById('lastSyncTime').textContent = 
        now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Show error message
function showError(message) {
    // Implement error notification system
    console.error(message);
}
