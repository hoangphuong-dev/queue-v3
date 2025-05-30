/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { onMounted, useState } from "@odoo/owl";

export class PatientSimpleController extends FormController {
    setup() {
        super.setup();

        // Chỉ chạy cho res.partner model
        if (this.props.resModel !== 'res.partner') {
            return;
        }

        this.rpc = useService("rpc");
        this.orm = useService("orm");

        this.coordinatorState = useState({
            isLoaded: false,
            error: null
        });

        onMounted(() => {
            this.setupCoordinatorDashboard();
        });
    }

    setupCoordinatorDashboard() {
        // Tìm container
        const container = this.el?.querySelector('.coordinator-container');

        if (!container || !this.model.root.resId) {
            return;
        }

        // Hiển thị loading
        container.innerHTML = `
            <div class="text-center py-4">
                <i class="fa fa-spinner fa-spin fa-2x mb-3"></i>
                <p>Đang tải dữ liệu...</p>
            </div>
        `;

        // Delay để đảm bảo data đã load
        setTimeout(() => {
            this.loadAndRenderData(container);
        }, 500);
    }

    async loadAndRenderData(container) {
        try {
            // Lấy data từ model
            const partnerData = this.model.root.data;

            // Parse JSON từ computed fields
            let nextServices = [];
            let priorityServices = [];

            if (partnerData.next_service_recommendations) {
                try {
                    nextServices = JSON.parse(partnerData.next_service_recommendations);
                } catch (e) {
                    console.log("Could not parse next_service_recommendations");
                }
            }

            if (partnerData.next_priority_services) {
                try {
                    priorityServices = JSON.parse(partnerData.next_priority_services);
                } catch (e) {
                    console.log("Could not parse next_priority_services");
                }
            }

            // Render HTML
            this.renderServices(container, nextServices, priorityServices);

        } catch (error) {
            console.error("Error loading coordinator data:", error);
            container.innerHTML = `
                <div class="alert alert-warning">
                    <i class="fa fa-exclamation-triangle me-2"></i>
                    Không thể tải dữ liệu. Lỗi: ${error.message}
                </div>
            `;
        }
    }

    renderServices(container, nextServices, priorityServices) {
        let html = '<div class="services-container">';

        // Render dịch vụ tiếp theo
        if (nextServices && nextServices.length > 0) {
            html += '<h6 class="mb-3">Dịch vụ tiếp theo:</h6>';

            nextServices.forEach((service, index) => {
                const bestRoom = service.available_rooms && service.available_rooms.length > 0
                    ? service.available_rooms[0] // Lấy phòng đầu tiên
                    : null;

                html += `
                    <div class="card mb-2">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-center">
                                <div>
                                    <h6 class="mb-1">${service.service_name || 'N/A'}</h6>
                                    <span class="badge bg-secondary">${service.service_code || 'N/A'}</span>
                                    ${bestRoom ? `
                                        <div class="small text-muted mt-1">
                                            Phòng: ${bestRoom.room_name} (${bestRoom.waiting_count || 0} người chờ)
                                        </div>
                                    ` : '<div class="small text-warning">Không có phòng khả dụng</div>'}
                                </div>
                                <button class="btn btn-primary btn-sm" 
                                        onclick="window.createToken_${index}()"
                                        ${!bestRoom ? 'disabled' : ''}>
                                    <i class="fa fa-plus"></i> Tạo token
                                </button>
                            </div>
                        </div>
                    </div>
                `;

                // Tạo function cho từng service
                window[`createToken_${index}`] = () => {
                    this.createToken(service.service_id, bestRoom ? bestRoom.room_id : null);
                };
            });
        } else {
            html += `
                <div class="alert alert-info">
                    <i class="fa fa-info-circle me-2"></i>
                    Không có dịch vụ tiếp theo
                </div>
            `;
        }

        // Render dịch vụ ưu tiên
        if (priorityServices && priorityServices.length > 0) {
            html += '<h6 class="mb-3 mt-4">Dịch vụ ưu tiên:</h6>';

            priorityServices.slice(0, 3).forEach((service, index) => {
                html += `
                    <div class="card mb-2 border-warning">
                        <div class="card-body py-2">
                            <div class="d-flex justify-content-between align-items-center">
                                <div>
                                    <strong>${service.service_name || 'N/A'}</strong>
                                    <span class="badge bg-warning text-dark ms-2">${service.room_name || 'N/A'}</span>
                                    <div class="small text-muted">
                                        Chờ: ${Math.round(service.estimated_wait_time || 0)} phút
                                    </div>
                                </div>
                                <button class="btn btn-warning btn-sm" 
                                        onclick="window.createPriorityToken_${index}()">
                                    <i class="fa fa-star"></i> Ưu tiên
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
        if (!serviceId) {
            alert('Lỗi: Không có service ID');
            return;
        }

        try {
            const result = await this.rpc('/coordinator/create_token', {
                patient_id: this.model.root.resId,
                service_id: serviceId,
                room_id: roomId,
                notes: 'Tạo từ chi tiết bệnh nhân'
            });

            if (result.success) {
                // Hiển thị thông báo
                this.showSuccessMessage(result.message);

                // Reload data
                await this.model.root.load();
                this.setupCoordinatorDashboard();
            } else {
                alert('Lỗi: ' + result.message);
            }
        } catch (error) {
            console.error('Error creating token:', error);
            alert('Không thể tạo token: ' + error.message);
        }
    }

    showSuccessMessage(message) {
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-success position-fixed';
        alertDiv.style.top = '20px';
        alertDiv.style.right = '20px';
        alertDiv.style.zIndex = '9999';
        alertDiv.innerHTML = `
            <strong>Thành công!</strong> ${message}
        `;
        document.body.appendChild(alertDiv);

        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 3000);
    }
}

export const patientSimpleFormView = {
    ...formView,
    Controller: PatientSimpleController,
};

registry.category("views").add("patient_detail_form", patientSimpleFormView);