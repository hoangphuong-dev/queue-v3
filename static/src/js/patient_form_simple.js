/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { onMounted, useState } from "@odoo/owl";

export class SimplePatientFormController extends FormController {
    setup() {
        super.setup();

        // Kiểm tra xem có phải patient form không
        if (this.props.resModel !== 'res.partner') {
            return;
        }

        this.orm = useService("orm");
        this.rpc = useService("rpc");

        this.coordinatorState = useState({
            isLoaded: false,
            error: null
        });

        onMounted(() => {
            // Delay một chút để đảm bảo DOM đã render
            setTimeout(() => {
                this.loadCoordinatorDashboard();
            }, 100);
        });
    }

    async loadCoordinatorDashboard() {
        const coordinatorContainer = this.el?.querySelector('.coordinator-container');

        if (!coordinatorContainer || !this.model.root.resId) {
            return;
        }

        try {
            // Hiển thị loading
            coordinatorContainer.innerHTML = `
                <div class="text-center py-4">
                    <i class="fa fa-spinner fa-spin fa-2x mb-3"></i>
                    <p>Đang tải dữ liệu điều phối...</p>
                </div>
            `;

            // Lấy dữ liệu từ các field computed
            const partnerData = this.model.root.data;

            // Parse JSON data từ computed fields
            let nextServices = [];
            let priorityServices = [];

            try {
                if (partnerData.next_service_recommendations) {
                    nextServices = JSON.parse(partnerData.next_service_recommendations);
                }
                if (partnerData.next_priority_services) {
                    priorityServices = JSON.parse(partnerData.next_priority_services);
                }
            } catch (e) {
                console.error("Error parsing service data:", e);
            }

            // Lấy thông tin token hiện tại
            let currentService = null;
            if (partnerData.current_active_token_id) {
                // Load thông tin chi tiết token
                const tokenData = await this.orm.read('queue.token', [partnerData.current_active_token_id[0]], [
                    'name', 'service_id', 'room_id', 'state', 'position', 'estimated_wait_time', 'start_time', 'emergency'
                ]);

                if (tokenData.length > 0) {
                    const token = tokenData[0];
                    currentService = {
                        token_id: token.id,
                        token_name: token.name,
                        service_name: token.service_id[1],
                        room_name: token.room_id ? token.room_id[1] : 'Chưa phân phòng',
                        room_code: token.room_id ? token.room_id[1].split(' ')[0] : '',
                        state: token.state,
                        position: token.position,
                        estimated_wait_time: token.estimated_wait_time,
                        start_time: token.start_time,
                        emergency: token.emergency
                    };
                }
            }

            this.renderCoordinatorData(coordinatorContainer, {
                next_services: nextServices,
                priority_services: priorityServices,
                current_service: currentService
            });

            this.coordinatorState.isLoaded = true;

        } catch (error) {
            console.error("Error loading coordinator dashboard:", error);
            this.showError(coordinatorContainer, 'Không thể tải dữ liệu điều phối');
        }
    }

    renderCoordinatorData(container, data) {
        const nextServices = data.next_services || [];
        const priorityServices = data.priority_services || [];
        const currentService = data.current_service;

        let html = '<div class="coordinator-data">';

        // Hiển thị dịch vụ hiện tại
        if (currentService) {
            html += `
                <div class="card mb-3 border-primary">
                    <div class="card-header bg-primary text-white">
                        <h6 class="mb-0">Đang thực hiện</h6>
                    </div>
                    <div class="card-body">
                        <h6 class="card-title">${currentService.service_name}</h6>
                        <p class="mb-1">Phòng: <strong>${currentService.room_name}</strong></p>
                        <p class="mb-1">Token: <strong>${currentService.token_name}</strong></p>
                        <span class="badge bg-${currentService.state === 'in_progress' ? 'success' : 'warning'}">
                            ${currentService.state === 'in_progress' ? 'Đang thực hiện' : 'Đang chờ'}
                        </span>
                        ${currentService.emergency ? '<span class="badge bg-danger ms-2">Khẩn cấp</span>' : ''}
                    </div>
                </div>
            `;
        }

        // Hiển thị dịch vụ tiếp theo
        if (nextServices.length > 0) {
            html += '<h6 class="mb-3">Dịch vụ tiếp theo:</h6>';
            nextServices.forEach((service, index) => {
                const bestRoom = service.available_rooms && service.available_rooms.length > 0
                    ? service.available_rooms.reduce((best, current) =>
                        current.estimated_wait_time < best.estimated_wait_time ? current : best)
                    : null;

                html += `
                    <div class="card mb-2">
                        <div class="card-body py-3">
                            <div class="d-flex justify-content-between align-items-center">
                                <div class="flex-grow-1">
                                    <h6 class="mb-1">${service.service_name}</h6>
                                    <div class="d-flex align-items-center mb-2">
                                        <span class="badge bg-secondary me-2">${service.service_code}</span>
                                        <span class="badge bg-info me-2">${service.estimated_duration || 15} phút</span>
                                    </div>
                                    ${bestRoom ? `
                                        <small class="text-muted">
                                            Phòng đề xuất: <strong>${bestRoom.room_name}</strong> 
                                            (${bestRoom.waiting_count} người chờ)
                                        </small>
                                    ` : '<small class="text-warning">Không có phòng khả dụng</small>'}
                                </div>
                                <div class="text-end">
                                    <button class="btn btn-primary btn-sm" 
                                            onclick="window.createTokenForService_${index}()"
                                            ${!bestRoom ? 'disabled' : ''}>
                                        <i class="fa fa-plus me-1"></i>Tạo token
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                `;

                // Tạo function riêng cho mỗi service
                window[`createTokenForService_${index}`] = () => {
                    this.createToken(service.service_id, bestRoom ? bestRoom.room_id : null);
                };
            });
        } else {
            html += `
                <div class="alert alert-info">
                    <i class="fa fa-info-circle me-2"></i>
                    Không có dịch vụ tiếp theo hoặc bệnh nhân đã hoàn thành tất cả dịch vụ
                </div>
            `;
        }

        // Hiển thị dịch vụ ưu tiên nếu có
        if (priorityServices.length > 0) {
            html += '<h6 class="mb-3 mt-4">Dịch vụ ưu tiên:</h6>';
            priorityServices.slice(0, 3).forEach((service, index) => {
                html += `
                    <div class="card mb-2 border-warning">
                        <div class="card-body py-2">
                            <div class="d-flex justify-content-between align-items-center">
                                <div>
                                    <strong>${service.service_name}</strong>
                                    <span class="badge bg-warning text-dark ms-2">${service.room_name}</span>
                                    <small class="text-muted d-block">
                                        Chờ: ${Math.round(service.estimated_wait_time)} phút | 
                                        Điểm: ${service.priority_score.toFixed(1)}
                                    </small>
                                </div>
                                <button class="btn btn-warning btn-sm" 
                                        onclick="window.createPriorityToken_${index}()">
                                    <i class="fa fa-star me-1"></i>Ưu tiên
                                </button>
                            </div>
                        </div>
                    </div>
                `;

                window[`createPriorityToken_${index}`] = () => {
                    this.createToken(service.service_id, service.room_id);
                };
            });
        }

        html += '</div>';
        container.innerHTML = html;
    }

    async createToken(serviceId, roomId) {
        try {
            const result = await this.rpc('/coordinator/create_token', {
                patient_id: this.model.root.resId,
                service_id: serviceId,
                room_id: roomId,
                notes: 'Tạo từ chi tiết bệnh nhân'
            });

            if (result.success) {
                // Hiển thị thông báo thành công
                const alertDiv = document.createElement('div');
                alertDiv.className = 'alert alert-success alert-dismissible fade show position-fixed';
                alertDiv.style.top = '20px';
                alertDiv.style.right = '20px';
                alertDiv.style.zIndex = '9999';
                alertDiv.innerHTML = `
                    <strong>Thành công!</strong> ${result.message}
                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                `;
                document.body.appendChild(alertDiv);

                // Tự động ẩn sau 3 giây
                setTimeout(() => {
                    if (alertDiv.parentNode) {
                        alertDiv.remove();
                    }
                }, 3000);

                // Reload data
                await this.model.root.load();
                this.loadCoordinatorDashboard();
            } else {
                alert('Lỗi: ' + result.message);
            }
        } catch (error) {
            console.error('Error creating token:', error);
            alert('Không thể tạo token: ' + error.message);
        }
    }

    showError(container, message) {
        container.innerHTML = `
            <div class="alert alert-danger">
                <i class="fa fa-exclamation-triangle me-2"></i>
                ${message}
                <button class="btn btn-sm btn-outline-primary ms-2" onclick="location.reload()">
                    <i class="fa fa-refresh"></i> Tải lại
                </button>
            </div>
        `;
    }
}

export const simplePatientFormView = {
    ...formView,
    Controller: SimplePatientFormController,
};

registry.category("views").add("patient_detail_form", simplePatientFormView);