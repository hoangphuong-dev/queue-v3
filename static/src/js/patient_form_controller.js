/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { CoordinatorDashboard } from "./coordinator_dashboard";
import { onMounted, useState } from "@odoo/owl";

export class PatientFormController extends FormController {
    setup() {
        super.setup();
        this.rpc = useService("rpc");

        this.coordinatorState = useState({
            isLoaded: false,
            dashboardComponent: null
        });

        onMounted(() => {
            this.mountCoordinatorDashboard();
        });
    }

    async mountCoordinatorDashboard() {
        const coordinatorContainer = this.el.querySelector('.coordinator-container');

        if (coordinatorContainer && this.model.root.resId) {
            try {
                // Clear existing content
                coordinatorContainer.innerHTML = '';

                // Create and mount coordinator dashboard
                const coordinatorDashboard = new CoordinatorDashboard(this, {
                    patient_id: this.model.root.resId
                });

                await coordinatorDashboard.mount(coordinatorContainer);
                this.coordinatorState.dashboardComponent = coordinatorDashboard;
                this.coordinatorState.isLoaded = true;

            } catch (error) {
                console.error("Error mounting coordinator dashboard:", error);
                coordinatorContainer.innerHTML = `
                    <div class="alert alert-warning">
                        <i class="fa fa-exclamation-triangle me-2"></i>
                        Không thể tải dữ liệu điều phối. Vui lòng thử lại.
                        <button class="btn btn-sm btn-outline-primary ms-2" onclick="location.reload()">
                            <i class="fa fa-refresh"></i> Tải lại
                        </button>
                    </div>
                `;
            }
        }
    }
}

export const patientFormView = {
    ...formView,
    Controller: PatientFormController,
};

registry.category("views").add("patient_detail_form", patientFormView);