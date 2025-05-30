/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { useService } from "@web/core/utils/hooks";

export class PatientDetailFormController extends FormController {
    setup() {
        super.setup();
        this.rpc = useService("rpc");
        this.coordinatorData = useState({
            loaded: false,
            nextServices: [],
            priorityServices: [],
            currentService: null
        });

        onWillStart(async () => {
            if (this.model.root.resId) {
                await this.loadCoordinatorData();
            }
        });
    }

    async loadCoordinatorData() {
        try {
            const result = await this.rpc('/coordinator/patient/' + this.model.root.resId + '/data');

            if (result.success) {
                this.coordinatorData.nextServices = result.next_services || [];
                this.coordinatorData.priorityServices = result.priority_services || [];
                this.coordinatorData.currentService = result.current_service;
                this.coordinatorData.loaded = true;
            }
        } catch (error) {
            console.error("Error loading coordinator data:", error);
        }
    }
}

export const patientDetailFormView = {
    ...formView,
    Controller: PatientDetailFormController,
};

registry.category("views").add("patient_detail_form", patientDetailFormView);