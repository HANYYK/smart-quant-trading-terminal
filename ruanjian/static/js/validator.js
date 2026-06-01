/**
 * 表单验证模块
 * 提供统一的表单验证和提交功能
 */

const FormValidator = {
    /**
     * 验证规则定义
     */
    rules: {
        required: {
            validate: function(value) {
                if (typeof value === 'string') return value.trim().length > 0;
                return value !== null && value !== undefined;
            },
            message: '此字段为必填项'
        },
        email: {
            validate: function(value) {
                if (!value) return true;
                return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
            },
            message: '请输入有效的邮箱地址'
        },
        number: {
            validate: function(value) {
                if (!value) return true;
                return !isNaN(parseFloat(value)) && isFinite(value);
            },
            message: '请输入有效的数字'
        },
        positive: {
            validate: function(value) {
                if (!value) return true;
                return parseFloat(value) > 0;
            },
            message: '请输入正数'
        },
        min: function(min) {
            return {
                validate: function(value) {
                    if (!value) return true;
                    return parseFloat(value) >= min;
                },
                message: `值不能小于 ${min}`
            };
        },
        max: function(max) {
            return {
                validate: function(value) {
                    if (!value) return true;
                    return parseFloat(value) <= max;
                },
                message: `值不能大于 ${max}`
            };
        },
        minLength: function(len) {
            return {
                validate: function(value) {
                    if (!value) return true;
                    return value.length >= len;
                },
                message: `至少需要 ${len} 个字符`
            };
        },
        maxLength: function(len) {
            return {
                validate: function(value) {
                    if (!value) return true;
                    return value.length <= len;
                },
                message: `最多只能输入 ${len} 个字符`
            };
        },
        pattern: function(regex, message) {
            return {
                validate: function(value) {
                    if (!value) return true;
                    return regex.test(value);
                },
                message: message || '格式不正确'
            };
        },
        stockCode: {
            validate: function(value) {
                if (!value) return true;
                return /^(sh|sz)\.\d{6}$/.test(value.toLowerCase());
            },
            message: '请输入有效的股票代码 (如: sh.600000)'
        },
        fundCode: {
            validate: function(value) {
                if (!value) return true;
                return /^\d{6}$/.test(value);
            },
            message: '请输入有效的基金代码 (6位数字)'
        }
    },

    /**
     * 创建验证器实例
     * @param {string} formId - 表单 ID
     * @param {Object} fields - 字段配置 {fieldName: [rules]}
     * @returns {Object} 验证器实例
     */
    create: function(formId, fields) {
        const form = document.getElementById(formId);
        if (!form) {
            console.error(`Form ${formId} not found`);
            return null;
        }

        const validator = {
            form: form,
            fields: fields,
            errors: {},

            /**
             * 验证单个字段
             * @param {string} fieldName - 字段名
             * @returns {boolean} 是否通过验证
             */
            validateField: function(fieldName) {
                const rules = this.fields[fieldName];
                if (!rules) return true;

                const input = this.form.querySelector(`[name="${fieldName}"]`);
                if (!input) return true;

                const value = input.value;
                let isValid = true;
                let errorMsg = '';

                for (const rule of rules) {
                    const ruleObj = typeof rule === 'string' ? FormValidator.rules[rule] : rule;
                    if (ruleObj && !ruleObj.validate(value)) {
                        isValid = false;
                        errorMsg = ruleObj.message;
                        break;
                    }
                }

                this.errors[fieldName] = isValid ? null : errorMsg;
                this.showError(input, errorMsg);
                return isValid;
            },

            /**
             * 显示错误信息
             * @param {HTMLElement} input - 输入元素
             * @param {string} message - 错误信息
             */
            showError: function(input, message) {
                const group = input.closest('.mb-3') || input.parentElement;
                let errorEl = group.querySelector('.invalid-feedback, .error-message');

                if (message) {
                    input.classList.add('is-invalid');
                    input.classList.remove('is-valid');
                    if (!errorEl) {
                        errorEl = document.createElement('div');
                        errorEl.className = 'invalid-feedback';
                        group.appendChild(errorEl);
                    }
                    errorEl.textContent = message;
                } else {
                    input.classList.remove('is-invalid');
                    input.classList.add('is-valid');
                    if (errorEl) errorEl.remove();
                }
            },

            /**
             * 验证所有字段
             * @returns {boolean} 是否全部通过验证
             */
            validate: function() {
                let isValid = true;
                for (const fieldName in this.fields) {
                    if (!this.validateField(fieldName)) {
                        isValid = false;
                    }
                }
                return isValid;
            },

            /**
             * 获取表单数据
             * @returns {Object} 表单数据
             */
            getData: function() {
                const data = {};
                const formData = new FormData(this.form);
                for (const [key, value] of formData.entries()) {
                    data[key] = value;
                }
                return data;
            },

            /**
             * 提交表单
             * @param {Function} onSuccess - 成功回调
             * @param {Function} onError - 错误回调
             */
            submit: function(onSuccess, onError) {
                if (!this.validate()) {
                    if (onError) onError(this.errors);
                    return;
                }

                const data = this.getData();
                const submitBtn = this.form.querySelector('[type="submit"]');
                const originalText = submitBtn ? submitBtn.textContent : '';

                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>提交中...';
                }

                fetch(this.form.action || window.location.href, {
                    method: 'POST',
                    body: new URLSearchParams(data),
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded'
                    }
                })
                .then(res => res.json())
                .then(result => {
                    if (result.success) {
                        AppUtils.showToast(result.message || '提交成功', 'success');
                        if (onSuccess) onSuccess(result);
                    } else {
                        AppUtils.showToast(result.error || '提交失败', 'error');
                        if (onError) onError(result);
                    }
                })
                .catch(err => {
                    console.error('Form submit error:', err);
                    AppUtils.showToast('网络错误，请稍后重试', 'error');
                    if (onError) onError(err);
                })
                .finally(() => {
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.textContent = originalText;
                    }
                });
            },

            /**
             * 重置表单
             */
            reset: function() {
                this.form.reset();
                this.errors = {};
                const inputs = this.form.querySelectorAll('.is-invalid, .is-valid');
                inputs.forEach(input => {
                    input.classList.remove('is-invalid', 'is-valid');
                });
            }
        };

        // 绑定实时验证
        for (const fieldName in fields) {
            const input = form.querySelector(`[name="${fieldName}"]`);
            if (input) {
                input.addEventListener('blur', () => validator.validateField(fieldName));
                input.addEventListener('input', () => {
                    if (validator.errors[fieldName]) {
                        validator.validateField(fieldName);
                    }
                });
            }
        }

        return validator;
    }
};

/**
 * 常用表单预定义
 */
const FormPresets = {
    /**
     * 股票代码表单验证
     */
    stockForm: function(formId) {
        return FormValidator.create(formId, {
            stock_code: ['required', 'stockCode'],
            quantity: ['required', 'number', 'positive']
        });
    },

    /**
     * 基金搜索表单验证
     */
    fundSearchForm: function(formId) {
        return FormValidator.create(formId, {
            fund_code: ['fundCode']
        });
    },

    /**
     * 登录表单验证
     */
    loginForm: function(formId) {
        return FormValidator.create(formId, {
            username: ['required'],
            password: ['required']
        });
    },

    /**
     * 注册表单验证
     */
    registerForm: function(formId) {
        return FormValidator.create(formId, {
            username: ['required', FormValidator.rules.minLength(3), FormValidator.rules.maxLength(20)],
            email: ['required', 'email'],
            password: ['required', FormValidator.rules.minLength(8)],
            password_confirm: ['required']
        });
    }
};
