/** @odoo-module **/

import {Component, useState, onWillStart, onMounted} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {_t} from "@web/core/l10n/translation";

export class CoordinatorDashboard extends Component {
    static template = "hospital_queue_management.CoordinatorDashboard";
    static props = {
        patient_id: {type: Number}
    };

    setup() {
        this.orm = useService("orm");
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        this.action = useService("action");

        this.state = useState({
            isLoading: true,
            patientData: {},
            currentService: null,
            nextServices: [],
            priorityServices: [],
            tokenHistory: [],
            roomStatus: [],
            selectedTab: 'services',
            showCreateTokenModal: false,
            selectedService: null,
            selectedRoom: null,
            customNotes: ''
        });

        onWillStart(async () => {
            await this.loadPatientData();
            await this.loadRoomStatus();
        });

        onMounted(() => {
            this.startAutoRefresh();
        });
    }

    async loadPatientData() {
        try {
            this.state.isLoading = true;
            const result = await this.rpc('/coordinator/patient/' + this.props.patient_id + '/data');

            if (result.success) {
                this.state.patientData = result.patient_info;
                this.state.currentService = result.current_service;
                this.state.tokenHistory = result.token_history;

                // Parse recommendations - đảm bảo là array
                if (result.recommendations && result.recommendations.next_services) {
                    this.state.nextServices = Array.isArray(result.recommendations.next_services) ? result.recommendations.next_services : [];
                } else {
                    this.state.nextServices = [];
                }

                // Parse priority services - đảm bảo là array
                if (result.priority_services && Array.isArray(result.priority_services)) {
                    this.state.priorityServices = result.priority_services.slice(0, 10);
                } else {
                    this.state.priorityServices = [];
                }

                console.log('Loaded next services:', this.state.nextServices);
                console.log('Loaded priority services:', this.state.priorityServices);
            } else {
                this.notification.add(result.message, {type: "danger"});
            }
        } catch (error) {
            console.error("Error loading patient data:", error);
            this.notification.add(_t("Lỗi khi tải dữ liệu bệnh nhân"), {type: "danger"});
        } finally {
            this.state.isLoading = false;
        }
    }

    async loadRoomStatus() {
        try {
            const result = await this.rpc('/coordinator/get_room_status');
            if (result.success) {
                this.state.roomStatus = result.rooms;
            }
        } catch (error) {
            console.error("Error loading room status:", error);
        }
    }

    startAutoRefresh() {
        setInterval(() => {
            this.loadPatientData();
            this.loadRoomStatus();
        }, 30000); // Refresh mỗi 30 giây
    }

    onTabChange(tabName) {
        this.state.selectedTab = tabName;
    }

    async onCreateToken(serviceData) {
        try {
            if (!serviceData.available_rooms || serviceData.available_rooms.length === 0) {
                this.notification.add(_t("Không có phòng khả dụng cho dịch vụ này"), {type: "warning"});
                return;
            }

            // Chọn phòng tối ưu nhất (thời gian chờ thấp nhất)
            const optimalRoom = serviceData.available_rooms.reduce((best, current) => current.estimated_wait_time < best.estimated_wait_time ? current : best);

            const result = await this.rpc('/coordinator/create_token', {
                patient_id: this.props.patient_id,
                service_id: serviceData.service_id,
                room_id: optimalRoom.room_id,
                notes: `Tạo từ điều phối - Dịch vụ ưu tiên`
            });

            if (result.success) {
                this.notification.add(result.message, {type: "success"});
                await this.loadPatientData();
            } else {
                this.notification.add(result.message, {type: "danger"});
            }
        } catch (error) {
            console.error("Error creating token:", error);
            this.notification.add(_t("Lỗi khi tạo token"), {type: "danger"});
        }
    }

    async onMoveToken(tokenId, newRoomId, reason = '') {
        try {
            const result = await this.rpc('/coordinator/move_token', {
                token_id: tokenId, new_room_id: newRoomId, reason: reason
            });

            if (result.success) {
                this.notification.add(result.message, {type: "success"});
                await this.loadPatientData();
            } else {
                this.notification.add(result.message, {type: "danger"});
            }
        } catch (error) {
            console.error("Error moving token:", error);
            this.notification.add(_t("Lỗi khi chuyển token"), {type: "danger"});
        }
    }

    async onOptimizeFlow() {
        try {
            const result = await this.rpc('/coordinator/optimize_patient_flow', {
                patient_id: this.props.patient_id
            });

            if (result.success) {
                this.notification.add(result.message, {type: "success"});

                if (result.optimized_tokens && result.optimized_tokens.length > 0) {
                    // Hiển thị chi tiết tối ưu hóa
                    const details = result.optimized_tokens.map(opt => `${opt.token_name}: ${opt.old_room} → ${opt.new_room} (Tiết kiệm ${Math.round(opt.estimated_time_saved)} phút)`).join('\n');

                    this.notification.add(`Chi tiết tối ưu hóa:\n${details}`, {
                        type: "info", sticky: true
                    });
                }

                await this.loadPatientData();
            } else {
                this.notification.add(result.message, {type: "warning"});
            }
        } catch (error) {
            console.error("Error optimizing flow:", error);
            this.notification.add(_t("Lỗi khi tối ưu luồng"), {type: "danger"});
        }
    }

    onCustomizeService(serviceData) {
        this.state.selectedService = serviceData;
        this.state.selectedRoom = null;
        this.state.customNotes = '';
        this.state.showCreateTokenModal = true;
    }

    async createCustomToken() {
        if (!this.state.selectedService || !this.state.selectedRoom) {
            this.notification.add(_t("Vui lòng chọn phòng"), {type: "warning"});
            return;
        }

        try {
            const result = await this.rpc('/coordinator/create_token', {
                patient_id: this.props.patient_id,
                service_id: this.state.selectedService.service_id,
                room_id: parseInt(this.state.selectedRoom),
                notes: this.state.customNotes
            });

            if (result.success) {
                this.notification.add(result.message, {type: "success"});
                this.state.showCreateTokenModal = false;
                await this.loadPatientData();
            } else {
                this.notification.add(result.message, {type: "danger"});
            }
        } catch (error) {
            console.error("Error creating custom token:", error);
            this.notification.add(_t("Lỗi khi tạo token tùy chỉnh"), {type: "danger"});
        }
    }

    showMoveTokenModal(token) {
        // Implement move token modal logic
        console.log("Show move token modal for:", token);
    }

    getServiceTypeBadgeClass(serviceCode) {
        const badgeClasses = {
            'BLOOD': 'bg-danger',
            'XRAY': 'bg-warning',
            'ULTRA': 'bg-info',
            'DOC': 'bg-success',
            'VITAL': 'bg-primary',
            'REG': 'bg-secondary',
            'PHARM': 'bg-dark'
        };
        return badgeClasses[serviceCode] || 'bg-secondary';
    }

    formatTime(minutes) {
        if (!minutes || minutes === 0) return '0 phút';
        const hours = Math.floor(minutes / 60);
        const mins = Math.floor(minutes % 60);
        return hours > 0 ? `${hours} giờ ${mins} phút` : `${mins} phút`;
    }

    getLoadStatusClass(loadPercentage) {
        if (loadPercentage >= 100) return 'bg-danger';
        if (loadPercentage >= 75) return 'bg-warning';
        if (loadPercentage >= 50) return 'bg-info';
        return 'bg-success';
    }

    getPatientCategoryBadge(category) {
        const badges = {
            'vvip': {class: 'bg-danger', text: 'VVIP'},
            'vip': {class: 'bg-warning', text: 'VIP'},
            'pregnant': {class: 'bg-pink', text: 'Thai phụ'},
            'child': {class: 'bg-info', text: 'Trẻ em'},
            'elderly': {class: 'bg-purple', text: 'Người già'},
            'nccvcm': {class: 'bg-success', text: 'NCCVCM'},
            'normal': {class: 'bg-secondary', text: 'Thường'}
        };
        return badges[category] || badges['normal'];
    }
}

registry.category("actions").add("coordinator_dashboard", CoordinatorDashboard);
